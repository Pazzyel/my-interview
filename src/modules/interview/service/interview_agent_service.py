import json
import re
import uuid
from datetime import datetime

from langgraph.types import Checkpointer
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from common.llm_provider import LlmProviderRegistry, LlmProviderResolver
from common.models import AsyncTaskStatus
from modules.interview.listener.evaluate_message_producer import EvaluateMessageProducer
from modules.interview.model.interview_agent_dto import (
    CreateInterviewRequest, CurrentQuestionResponse, InterviewQuestionDTO,
    InterviewReportDTO, InterviewSessionDTO,
    SessionListItemDTO, SubmitAnswerRequest, SubmitAnswerResponse,
)
from modules.interview.model.interview_dto import InterviewDetailDTO
from modules.interview.model.interview_entity import InterviewSessionEntity, SessionStatus
from modules.interview.repository.interview_repository import InterviewRepository
from modules.interview.service.interview_creation_coordinator import InterviewCreationCoordinator
from modules.interview.service.interview_evaluation_agent_service import InterviewEvaluationAgentService
from modules.interview.service.interview_question_agent_service import InterviewQuestionAgentService
from modules.interview.service.interview_skill_service import InterviewSkillService


class InterviewAgentService:
    """Skill-driven text interview orchestration and lifecycle service."""

    REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

    def __init__(
        self,
        interview_repository: InterviewRepository,
        evaluate_message_producer: EvaluateMessageProducer,
        skill_service: InterviewSkillService | None = None,
        llm_provider_resolver: LlmProviderResolver | None = None,
        creation_coordinator: InterviewCreationCoordinator | None = None,
    ) -> None:
        self.interview_repository = interview_repository
        self.evaluate_message_producer = evaluate_message_producer
        self.skill_service = skill_service or InterviewSkillService()
        self.llm_provider_resolver = llm_provider_resolver or LlmProviderRegistry()
        self.creation_coordinator = creation_coordinator or InterviewCreationCoordinator()
        self.question_agent_service = InterviewQuestionAgentService(self.skill_service, self.llm_provider_resolver)
        self.evaluation_agent_service = InterviewEvaluationAgentService(self.llm_provider_resolver)

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        await self.question_agent_service.build_graph(checkpointer)
        await self.evaluation_agent_service.build_graph(checkpointer)

    async def create_session(self, db: AsyncSession, request: CreateInterviewRequest) -> InterviewSessionDTO:
        request_id = request.request_id.strip() if request.request_id else None
        if request_id and self.REQUEST_ID_PATTERN.fullmatch(request_id) is None:
            raise BusinessException(ErrorCode.BAD_REQUEST, "requestId 仅允许 8-64 位字母、数字、下划线或连字符")
        if request_id:
            async with self.creation_coordinator.lock(db, request_id):
                existing = await self.interview_repository.find_by_request_id(db, request_id)
                if existing is not None:
                    return await self._restore_session(db, existing)
                result = await self._create_session_internal(db, request, request_id)
                # Commit while holding the cross-instance MySQL named lock.
                await db.commit()
                return result
        return await self._create_session_internal(db, request, None)

    async def _create_session_internal(
        self, db: AsyncSession, request: CreateInterviewRequest, request_id: str | None
    ) -> InterviewSessionDTO:
        provider = request.llm_provider.strip() if request.llm_provider and request.llm_provider.strip() else "default"
        if request.skill_id == InterviewSkillService.CUSTOM_SKILL_ID:
            if not request.custom_categories:
                raise BusinessException(ErrorCode.BAD_REQUEST, "自定义面试必须提供 customCategories")
        else:
            self.skill_service.get_skill(request.skill_id)

        if request.resume_id is not None and not request.force_create:
            existing = await self.interview_repository.find_unfinished(db, request.resume_id, request.skill_id)
            if existing is not None:
                if request_id:
                    await self.interview_repository.bind_request_id(db, existing.sessionId, request_id)
                return await self._restore_session(db, existing)

        history = await self.interview_repository.list_historical_questions(db, request.skill_id, request.resume_id)
        session_id = uuid.uuid4().hex[:16]
        questions = await self.question_agent_service.generate_questions(
            resume_text=request.resume_text, question_count=request.question_count,
            historical_questions=history, session_id=session_id,
            skill_id=request.skill_id, difficulty=request.difficulty,
            custom_categories=request.custom_categories, jd_text=request.jd_text,
            llm_provider=provider,
        )
        await self.interview_repository.create_session(
            db=db, session_id=session_id, resume_id=request.resume_id,
            total_questions=len(questions), questions_json=self._serialize_questions(questions),
            request_id=request_id, skill_id=request.skill_id,
            difficulty=request.difficulty.value, llm_provider=provider,
        )
        return InterviewSessionDTO(
            session_id=session_id, resume_text=request.resume_text,
            total_questions=len(questions), current_question_index=0,
            questions=questions, status=SessionStatus.CREATED.value,
            evaluate_status=AsyncTaskStatus.PENDING.value,
        )

    async def list_sessions(self, db: AsyncSession) -> list[SessionListItemDTO]:
        return await self.interview_repository.list_sessions(db)

    async def get_session(self, db: AsyncSession, session_id: str) -> InterviewSessionDTO:
        entity = await self.interview_repository.find_by_session_id(db, session_id)
        if entity is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")
        return await self._restore_session(db, entity)

    async def get_current_question(self, db: AsyncSession, session_id: str) -> CurrentQuestionResponse:
        session = await self.get_session(db, session_id)
        if session.current_question_index >= len(session.questions):
            return CurrentQuestionResponse(completed=True, message="所有问题已回答完毕")
        if session.status == SessionStatus.CREATED.value:
            await self.interview_repository.update_session_status(db, session_id, SessionStatus.IN_PROGRESS.value)
        return CurrentQuestionResponse(completed=False, question=session.questions[session.current_question_index])

    async def save_answer(self, db: AsyncSession, session_id: str, request: SubmitAnswerRequest) -> None:
        session = await self.get_session(db, session_id)
        questions = self._apply_answer_to_questions(session.questions, request.question_index, request.answer)
        await self.interview_repository.update_session_questions_json(db, session_id, self._serialize_questions(questions))
        await self._upsert_answer(db, session_id, questions[request.question_index])
        if session.status == SessionStatus.CREATED.value:
            await self.interview_repository.update_session_status(db, session_id, SessionStatus.IN_PROGRESS.value)

    async def submit_answer(self, db: AsyncSession, session_id: str, request: SubmitAnswerRequest) -> SubmitAnswerResponse:
        session = await self.get_session(db, session_id)
        questions = self._apply_answer_to_questions(session.questions, request.question_index, request.answer)
        new_index = request.question_index + 1
        has_next = new_index < len(questions)
        status = SessionStatus.IN_PROGRESS.value if has_next else SessionStatus.COMPLETED.value
        await self.interview_repository.update_session_progress(
            db, session_id, new_index, status, self._serialize_questions(questions)
        )
        await self._upsert_answer(db, session_id, questions[request.question_index])
        if not has_next:
            await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.PENDING.value, None)
            self.evaluate_message_producer.send_evaluate_task(session_id)
        return SubmitAnswerResponse(
            has_next_question=has_next,
            next_question=questions[new_index] if has_next else None,
            current_index=new_index, total_questions=len(questions),
        )

    async def complete_interview(self, db: AsyncSession, session_id: str) -> None:
        session = await self.get_session(db, session_id)
        if session.status in {SessionStatus.COMPLETED.value, SessionStatus.EVALUATED.value}:
            return
        await self.interview_repository.update_session_status(db, session_id, SessionStatus.COMPLETED.value)
        await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.PENDING.value, None)
        self.evaluate_message_producer.send_evaluate_task(session_id)

    async def generate_report(self, db: AsyncSession, session_id: str) -> InterviewReportDTO:
        entity = await self.interview_repository.find_by_session_id(db, session_id)
        if entity is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")
        session = await self._restore_session(db, entity)
        if session.status not in {SessionStatus.COMPLETED.value, SessionStatus.EVALUATED.value}:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "面试尚未完成，无法生成报告")
        await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.PROCESSING.value, None)
        report = await self.evaluation_agent_service.evaluate(
            resume_text=session.resume_text, questions=session.questions,
            thread_id=f"interview-evaluate-{session_id}", session_id=session_id,
            llm_provider=entity.llmProvider,
            reference_context=self.skill_service.build_evaluation_reference_section_safe(entity.skillId),
        )
        await self.interview_repository.save_report(
            db, session_id, report.overall_score, report.overall_feedback,
            json.dumps(report.strengths, ensure_ascii=False),
            json.dumps(report.improvements, ensure_ascii=False),
            json.dumps([item.model_dump(by_alias=True) for item in report.reference_answers], ensure_ascii=False),
        )
        refs = {item.question_index: item for item in report.reference_answers}
        for item in report.question_details:
            ref = refs.get(item.question_index)
            await self.interview_repository.upsert_answer(
                db, session_id, item.question_index, item.question, item.category,
                item.user_answer, item.score, item.feedback,
                ref.reference_answer if ref else None,
                json.dumps(ref.key_points, ensure_ascii=False) if ref else None,
            )
        await self.interview_repository.update_session_status(db, session_id, SessionStatus.EVALUATED.value)
        await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.COMPLETED.value, None)
        return report

    async def export_report_pdf(self, db: AsyncSession, session_id: str) -> tuple[str, bytes]:
        detail: InterviewDetailDTO | None = await self.interview_repository.find_detail_by_session_id(db, session_id)
        if detail is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")
        if detail.evaluateStatus != AsyncTaskStatus.COMPLETED or detail.overallScore is None:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "评估结果尚未完成")
        lines = [
            f"模拟面试报告 {session_id}", f"生成时间 {datetime.now().isoformat()}", "",
            f"总分 {detail.overallScore}", f"总体评价 {detail.overallFeedback or ''}", "",
            "优势", *[f"- {item}" for item in detail.strengths], "",
            "改进建议", *[f"- {item}" for item in detail.improvements],
        ]
        return f"interview_report_{session_id}.pdf", "\n".join(lines).encode("utf-8")

    async def _restore_session(self, db: AsyncSession, entity: InterviewSessionEntity) -> InterviewSessionDTO:
        resume_text = await self.interview_repository.get_resume_text_by_session_id(db, entity.sessionId)
        return self._to_session_dto(entity, resume_text)

    async def _upsert_answer(self, db: AsyncSession, session_id: str, question: InterviewQuestionDTO) -> None:
        await self.interview_repository.upsert_answer(
            db, session_id, question.question_index, question.question, question.category,
            question.user_answer, question.score, question.feedback,
            question.reference_answer,
            json.dumps(question.key_points, ensure_ascii=False) if question.key_points else None,
        )

    def _apply_answer_to_questions(
        self, questions: list[InterviewQuestionDTO], question_index: int, answer: str
    ) -> list[InterviewQuestionDTO]:
        if question_index < 0 or question_index >= len(questions):
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "无效的问题索引")
        updated = [item.model_copy(deep=True) for item in questions]
        updated[question_index].user_answer = answer
        return updated

    @staticmethod
    def _serialize_questions(questions: list[InterviewQuestionDTO]) -> str:
        return json.dumps([item.model_dump(by_alias=True) for item in questions], ensure_ascii=False)

    def _to_session_dto(self, entity: InterviewSessionEntity, resume_text: str) -> InterviewSessionDTO:
        return InterviewSessionDTO(
            session_id=entity.sessionId, resume_text=resume_text,
            total_questions=entity.totalQuestions,
            current_question_index=entity.currentQuestionIndex,
            questions=self._deserialize_questions(entity.questionsJson),
            status=entity.status.value,
            evaluate_status=entity.evaluateStatus.value if entity.evaluateStatus else None,
            evaluate_error=entity.evaluateError,
        )

    @staticmethod
    def _deserialize_questions(raw: str | None) -> list[InterviewQuestionDTO]:
        if not raw:
            return []
        try:
            return [InterviewQuestionDTO.model_validate(item) for item in json.loads(raw)]
        except Exception:
            return []

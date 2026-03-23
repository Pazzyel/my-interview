import json
import uuid
from datetime import datetime

from langgraph.types import Checkpointer
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from common.models import AsyncTaskStatus
from modules.interview.listener.evaluate_message_producer import EvaluateMessageProducer
from modules.interview.model.interview_agent_dto import (
    CreateInterviewRequest,
    CurrentQuestionResponse,
    InterviewQuestionDTO,
    InterviewReportDTO,
    InterviewSessionDTO,
    ReferenceAnswerDTO,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from modules.interview.model.interview_dto import InterviewDetailDTO
from modules.interview.model.interview_entity import InterviewSessionEntity, SessionStatus
from modules.interview.repository.interview_repository import InterviewRepository
from modules.interview.service.interview_evaluation_agent_service import (
    InterviewEvaluationAgentService,
)
from modules.interview.service.interview_question_agent_service import (
    InterviewQuestionAgentService,
)


class InterviewAgentService:
    """
    面试编排服务，负责会话生命周期、仓储写入和 Agent 图调用。

    Interview orchestration service that manages session lifecycle,
    repository persistence, and delegated agent graph execution.
    """

    def __init__(
        self,
        interview_repository: InterviewRepository,
        evaluate_message_producer: EvaluateMessageProducer,
    ) -> None:
        self.interview_repository: InterviewRepository = interview_repository
        self.evaluate_message_producer: EvaluateMessageProducer = evaluate_message_producer
        self.question_agent_service: InterviewQuestionAgentService = InterviewQuestionAgentService()
        self.evaluation_agent_service: InterviewEvaluationAgentService = InterviewEvaluationAgentService()

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        await self.question_agent_service.build_graph(checkpointer)
        await self.evaluation_agent_service.build_graph(checkpointer)

    async def create_session(self, db: AsyncSession, request: CreateInterviewRequest) -> InterviewSessionDTO:
        """
        创建面试会话，执行未完成会话复用、历史题注入、图生成与持久化。

        Create an interview session with unfinished-session reuse,
        historical question injection, graph execution, and persistence.
        """
        if request.resume_id is None:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "创建面试会话必须提供 resumeId")

        # 检测该简历之前是否还要未完成的面试
        existing_session: InterviewSessionDTO | None = None
        if not request.force_create:
            existing_session = await self._find_unfinished_session_dto(db, request.resume_id)
        if existing_session is not None:
            return existing_session

        # 查找该简历之前的所有问过的问题，避免新一轮面试重复
        history_questions: list[str] = await self.interview_repository.list_historical_questions_by_resume_id(
            db, request.resume_id
        )


        # 调用面试官Agent生成本轮面试的所有问题
        session_id: str = uuid.uuid4().hex[:16]
        questions: list[InterviewQuestionDTO] = await self.question_agent_service.generate_questions(
            resume_text=request.resume_text,
            question_count=request.question_count,
            historical_questions=history_questions,
            session_id=session_id,
        )
        total_questions: int = len(questions)
        await self.interview_repository.create_session(
            db=db,
            session_id=session_id,
            resume_id=request.resume_id,
            total_questions=total_questions,
            questions_json=self._serialize_questions(questions),
        )
        return InterviewSessionDTO(
            session_id=session_id,
            resume_text=request.resume_text,
            total_questions=total_questions,
            current_question_index=0,
            questions=questions,
            status=SessionStatus.CREATED.value,
            evaluate_status=AsyncTaskStatus.PENDING.value,
            evaluate_error=None,
        )

    async def get_session(self, db: AsyncSession, session_id: str) -> InterviewSessionDTO:
        """获取面试会话"""
        session_entity: InterviewSessionEntity | None = await self.interview_repository.find_by_session_id(db, session_id)
        if session_entity is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")
        resume_text: str = await self.interview_repository.get_resume_text_by_session_id(db, session_id)
        return self._to_session_dto(session_entity, resume_text)

    async def get_current_question(self, db: AsyncSession, session_id: str) -> CurrentQuestionResponse:
        """获取当前面试回答到第几个问题"""
        session_dto: InterviewSessionDTO = await self.get_session(db, session_id)
        current_index: int = session_dto.current_question_index
        if current_index >= len(session_dto.questions):
            return CurrentQuestionResponse(completed=True, message="所有问题已回答完毕", question=None)
        # 只要尝试获取当前问题，而且不少IN_PROGRESS状态，说明是刚开始面试，修改状态
        if session_dto.status == SessionStatus.CREATED.value:
            await self.interview_repository.update_session_status(db, session_id, SessionStatus.IN_PROGRESS.value)
            session_dto.status = SessionStatus.IN_PROGRESS.value
        return CurrentQuestionResponse(completed=False, question=session_dto.questions[current_index])

    async def save_answer(self, db: AsyncSession, session_id: str, request: SubmitAnswerRequest) -> None:
        """保存用户的面试作答，但是这个问题还可以继续修改，不推进"""
        session_dto: InterviewSessionDTO = await self.get_session(db, session_id)
        updated_questions: list[InterviewQuestionDTO] = self._apply_answer_to_questions(
            session_dto.questions,
            request.question_index,
            request.answer,
        )
        await self.interview_repository.update_session_questions_json(
            db,
            session_id,
            self._serialize_questions(updated_questions),
        )
        await self.interview_repository.upsert_answer(
            db=db,
            session_id=session_id,
            question_index=request.question_index,
            question=updated_questions[request.question_index].question,
            category=updated_questions[request.question_index].category,
            user_answer=request.answer,
            score=None,
            feedback=None,
            reference_answer=None,
            key_points_json=None,
        )
        if session_dto.status == SessionStatus.CREATED.value:
            await self.interview_repository.update_session_status(db, session_id, SessionStatus.IN_PROGRESS.value)

    async def submit_answer(self, db: AsyncSession, session_id: str, request: SubmitAnswerRequest) -> SubmitAnswerResponse:
        """
        提交答案并推进题目游标，必要时切换会话状态到已完成。

        Submit answer and move question cursor; mark session completed when needed.
        """
        session_dto: InterviewSessionDTO = await self.get_session(db, session_id)
        updated_questions: list[InterviewQuestionDTO] = self._apply_answer_to_questions(
            session_dto.questions,
            request.question_index,
            request.answer,
        )

        # 推进问题
        new_index: int = request.question_index + 1
        has_next_question: bool = new_index < len(updated_questions)
        new_status: str = SessionStatus.IN_PROGRESS.value if has_next_question else SessionStatus.COMPLETED.value
        await self.interview_repository.update_session_progress(
            db,
            session_id,
            current_question_index=new_index,
            status=new_status,
            questions_json=self._serialize_questions(updated_questions),
        )
        await self.interview_repository.upsert_answer(
            db=db,
            session_id=session_id,
            question_index=request.question_index,
            question=updated_questions[request.question_index].question,
            category=updated_questions[request.question_index].category,
            user_answer=request.answer,
            score=None,
            feedback=None,
            reference_answer=None,
            key_points_json=None,
        )

        # 所有问题回答完毕后，发送 MQ 任务，由消费者异步执行评估
        if not has_next_question:
            await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.PENDING.value, None)
            self.evaluate_message_producer.send_evaluate_task(session_id)
        next_question: InterviewQuestionDTO | None = updated_questions[new_index] if has_next_question else None
        return SubmitAnswerResponse(
            has_next_question=has_next_question,
            next_question=next_question,
            current_index=new_index,
            total_questions=len(updated_questions),
        )

    async def complete_interview(self, db: AsyncSession, session_id: str) -> None:
        """完成面试（用户主动提前交卷）"""
        session_dto: InterviewSessionDTO = await self.get_session(db, session_id)
        if session_dto.status in {SessionStatus.COMPLETED.value, SessionStatus.EVALUATED.value}:
            return
        await self.interview_repository.update_session_status(db, session_id, SessionStatus.COMPLETED.value)
        await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.PENDING.value, None)
        self.evaluate_message_producer.send_evaluate_task(session_id)

    async def generate_report(self, db: AsyncSession, session_id: str) -> InterviewReportDTO:
        """
        生成面试评估报告

        可以是用户主动调用或者面试完成MQ消费者调用
        """
        session_dto: InterviewSessionDTO = await self.get_session(db, session_id)
        if session_dto.status not in {SessionStatus.COMPLETED.value, SessionStatus.EVALUATED.value}:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "面试尚未完成，无法生成报告")

        await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.PROCESSING.value, None)
        report: InterviewReportDTO = await self.evaluation_agent_service.evaluate(
            resume_text=session_dto.resume_text,
            questions=session_dto.questions,
            thread_id=f"interview-evaluate-{session_id}",
        )
        await self.interview_repository.save_report(
            db=db,
            session_id=session_id,
            overall_score=report.overall_score,
            overall_feedback=report.overall_feedback,
            strengths_json=json.dumps(report.strengths, ensure_ascii=False),
            improvements_json=json.dumps(report.improvements, ensure_ascii=False),
            reference_answers_json=json.dumps(
                [item.model_dump(by_alias=True) for item in report.reference_answers],
                ensure_ascii=False,
            ),
        )
        for item in report.question_details:
            matched_ref: ReferenceAnswerDTO | None = next(
                (ref for ref in report.reference_answers if ref.question_index == item.question_index),
                None,
            )
            await self.interview_repository.upsert_answer(
                db=db,
                session_id=session_id,
                question_index=item.question_index,
                question=item.question,
                category=item.category,
                user_answer=item.user_answer,
                score=item.score,
                feedback=item.feedback,
                reference_answer=matched_ref.reference_answer if matched_ref is not None else None,
                key_points_json=(
                    json.dumps(matched_ref.key_points, ensure_ascii=False)
                    if matched_ref is not None
                    else None
                ),
            )
        await self.interview_repository.update_session_status(db, session_id, SessionStatus.EVALUATED.value)
        await self.interview_repository.update_evaluate_status(db, session_id, AsyncTaskStatus.COMPLETED.value, None)
        return report

    async def export_report_pdf(self, db: AsyncSession, session_id: str) -> tuple[str, bytes]:
        detail: InterviewDetailDTO | None = await self.interview_repository.find_detail_by_session_id(db, session_id)
        if detail is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")

        if (
            detail.evaluateStatus != AsyncTaskStatus.COMPLETED
            or detail.overallScore is None
            or detail.overallFeedback is None
        ):
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "评估结果还没完成")

        lines: list[str] = [
            f"模拟面试报告 {session_id}",
            f"生成时间 {datetime.now().isoformat()}",
            "",
            f"总分 {detail.overallScore}",
            f"总体评价 {detail.overallFeedback}",
            "",
            "优势",
            *[f"- {text}" for text in detail.strengths],
            "",
            "改进建议",
            *[f"- {text}" for text in detail.improvements],
        ]
        content: str = "\n".join(lines)
        return f"interview_report_{session_id}.pdf", content.encode("utf-8")

    def _serialize_questions(self, questions: list[InterviewQuestionDTO]) -> str:
        payload: list[dict[str, object]] = [item.model_dump(by_alias=True) for item in questions]
        return json.dumps(payload, ensure_ascii=False)

    def _apply_answer_to_questions(
        self,
        questions: list[InterviewQuestionDTO],
        question_index: int,
        answer: str,
    ) -> list[InterviewQuestionDTO]:
        """生成新的问题列表（更新了问题的回答）"""
        if question_index < 0 or question_index >= len(questions):
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "无效的问题索引")
        updated_questions: list[InterviewQuestionDTO] = [item.model_copy(deep=True) for item in questions]
        updated_questions[question_index].user_answer = answer
        return updated_questions

    async def _find_unfinished_session_dto(self, db: AsyncSession, resume_id: int) -> InterviewSessionDTO | None:
        entity: InterviewSessionEntity | None = await self.interview_repository.find_unfinished_by_resume_id(db, resume_id)
        if entity is None:
            return None
        resume_text: str = await self.interview_repository.get_resume_text_by_session_id(db, entity.sessionId)
        return self._to_session_dto(entity, resume_text)

    def _to_session_dto(self, entity: InterviewSessionEntity, resume_text: str) -> InterviewSessionDTO:
        questions: list[InterviewQuestionDTO] = self._deserialize_questions(entity.questionsJson)
        return InterviewSessionDTO(
            session_id=entity.sessionId,
            resume_text=resume_text,
            total_questions=entity.totalQuestions,
            current_question_index=entity.currentQuestionIndex,
            questions=questions,
            status=entity.status.value,
            evaluate_status=entity.evaluateStatus.value if entity.evaluateStatus is not None else None,
            evaluate_error=entity.evaluateError,
        )

    def _deserialize_questions(self, questions_json: str | None) -> list[InterviewQuestionDTO]:
        if questions_json is None or questions_json.strip() == "":
            return []
        try:
            parsed: list[dict[str, object]] = json.loads(questions_json)
            return [InterviewQuestionDTO.model_validate(item) for item in parsed]
        except Exception:
            return []

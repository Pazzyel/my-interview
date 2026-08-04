from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.models import AsyncTaskStatus
from modules.interview.model.interview_agent_dto import InterviewQuestionDTO
from modules.interview.service.interview_evaluation_agent_service import InterviewEvaluationAgentService
from modules.interview.service.interview_skill_service import InterviewSkillService
from modules.resume.repository.resume_repository import ResumeRepository
from modules.voiceinterview.model.voice_interview_entity import VoiceInterviewEvaluationEntity
from modules.voiceinterview.repository.evaluation_repository import VoiceInterviewEvaluationRepository
from modules.voiceinterview.repository.message_repository import VoiceInterviewMessageRepository
from modules.voiceinterview.repository.session_repository import VoiceInterviewSessionRepository


class VoiceInterviewEvaluationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sessions: VoiceInterviewSessionRepository,
        messages: VoiceInterviewMessageRepository,
        evaluations: VoiceInterviewEvaluationRepository,
        resume_repository: ResumeRepository,
        evaluator: InterviewEvaluationAgentService,
        skill_service: InterviewSkillService,
    ) -> None:
        self._session_factory = session_factory
        self._sessions = sessions
        self._messages = messages
        self._evaluations = evaluations
        self._resumes = resume_repository
        self._evaluator = evaluator
        self._skills = skill_service

    async def process(self, session_id: int) -> None:
        claim_updated_at: datetime | None = None
        async with self._session_factory() as db:
            session = await self._sessions.find_by_id(db, session_id)
            if session is None or session.evaluate_status == AsyncTaskStatus.COMPLETED:
                return
            if not await self._sessions.claim_evaluation(db, session_id):
                return
            await db.commit()
            claimed = await self._sessions.find_by_id(db, session_id)
            if claimed is None:
                return
            claim_updated_at = claimed.updated_at

        try:
            async with self._session_factory() as db:
                session = await self._sessions.find_by_id(db, session_id)
                if session is None:
                    return
                rows = await self._messages.list_for_context(db, session_id)
                questions = [
                    InterviewQuestionDTO(
                        question_index=index,
                        question=row.ai_generated_text or "",
                        type=(row.phase.value if row.phase else "VOICE"),
                        category=(row.phase.value if row.phase else "VOICE"),
                        user_answer=row.user_recognized_text,
                    )
                    for index, row in enumerate(
                        [item for item in rows if item.ai_generated_text and item.user_recognized_text],
                        start=1,
                    )
                ]
                resume_text = ""
                if session.resume_id is not None:
                    resume = await self._resumes.find_by_id(db, session.resume_id)
                    resume_text = str(getattr(resume, "resumeText", "") or "") if resume else ""
                reference = self._skills.build_evaluation_reference_section_safe(session.skill_id)

            report = await self._evaluator.evaluate(
                resume_text=resume_text,
                questions=questions,
                thread_id=f"voice-evaluate-{session_id}",
                session_id=str(session_id),
                llm_provider=session.llm_provider,
                reference_context=reference,
            )
            references = {item.question_index: item for item in report.reference_answers}
            answers = []
            for detail in report.question_details:
                ref = references.get(detail.question_index)
                answers.append(
                    {
                        **detail.model_dump(by_alias=True),
                        "referenceAnswer": ref.reference_answer if ref else None,
                        "keyPoints": ref.key_points if ref else [],
                    }
                )
            entity = VoiceInterviewEvaluationEntity(
                session_id=session_id,
                overall_score=report.overall_score,
                overall_feedback=report.overall_feedback,
                question_evaluations_json=json.dumps(answers, ensure_ascii=False),
                strengths_json=json.dumps(report.strengths, ensure_ascii=False),
                improvements_json=json.dumps(report.improvements, ensure_ascii=False),
                reference_answers_json=json.dumps(
                    [item.model_dump(by_alias=True) for item in report.reference_answers],
                    ensure_ascii=False,
                ),
                interviewer_role=session.skill_id,
                interview_date=session.end_time or datetime.now(),
            )
            async with self._session_factory() as db:
                if await self._sessions.find_by_id(db, session_id) is None:
                    return
                await self._evaluations.upsert(db, entity)
                completed = await self._sessions.finish_evaluation_claim(
                    db,
                    session_id,
                    claim_updated_at,
                    AsyncTaskStatus.COMPLETED,
                    None,
                )
                if not completed:
                    await db.rollback()
                    return
                await db.commit()
        except Exception as error:
            await self.mark_failed(session_id, str(error), claim_updated_at)
            raise

    async def mark_failed(
        self, session_id: int, error: str, claim_updated_at: datetime | None = None
    ) -> None:
        async with self._session_factory() as db:
            session = await self._sessions.find_by_id(db, session_id)
            if session is None or session.evaluate_status == AsyncTaskStatus.COMPLETED:
                return
            truncated = (error or "unknown evaluation error")[:500]
            if claim_updated_at is not None:
                await self._sessions.finish_evaluation_claim(
                    db, session_id, claim_updated_at, AsyncTaskStatus.FAILED, truncated
                )
            elif session.evaluate_status in {AsyncTaskStatus.PENDING, AsyncTaskStatus.FAILED}:
                await self._sessions.update_fields(
                    db, session_id, evaluate_status=AsyncTaskStatus.FAILED, evaluate_error=truncated
                )
            await db.commit()

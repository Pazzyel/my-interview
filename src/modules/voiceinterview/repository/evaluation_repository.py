import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import VoiceInterviewEvaluationORM
from modules.voiceinterview.model.voice_interview_dto import VoiceEvaluationDetailDTO
from modules.voiceinterview.model.voice_interview_entity import VoiceInterviewEvaluationEntity


class VoiceInterviewEvaluationRepository:
    async def find_by_session_id(
        self, db: AsyncSession, session_id: int
    ) -> VoiceInterviewEvaluationEntity | None:
        result = await db.execute(
            select(VoiceInterviewEvaluationORM).where(VoiceInterviewEvaluationORM.session_id == session_id)
        )
        item = result.scalar_one_or_none()
        return VoiceInterviewEvaluationEntity.model_validate(item) if item else None

    async def upsert(
        self, db: AsyncSession, entity: VoiceInterviewEvaluationEntity
    ) -> VoiceInterviewEvaluationEntity:
        result = await db.execute(
            select(VoiceInterviewEvaluationORM).where(VoiceInterviewEvaluationORM.session_id == entity.session_id)
        )
        orm = result.scalar_one_or_none()
        values = entity.model_dump(exclude={"id", "created_at"}, by_alias=False)
        if orm is None:
            orm = VoiceInterviewEvaluationORM(**values)
            db.add(orm)
        else:
            for key, value in values.items():
                setattr(orm, key, value)
        await db.flush()
        return VoiceInterviewEvaluationEntity.model_validate(orm)

    async def get_detail(self, db: AsyncSession, session_id: int) -> VoiceEvaluationDetailDTO | None:
        entity = await self.find_by_session_id(db, session_id)
        if entity is None:
            return None
        answers = self._json_list(entity.question_evaluations_json)
        return VoiceEvaluationDetailDTO(
            session_id=session_id, overall_score=entity.overall_score,
            overall_feedback=entity.overall_feedback,
            total_questions=len(answers), question_evaluations=answers, answers=answers,
            strengths=[str(item) for item in self._json_list(entity.strengths_json)],
            improvements=[str(item) for item in self._json_list(entity.improvements_json)],
            reference_answers=self._json_list(entity.reference_answers_json),
            interviewer_role=entity.interviewer_role, interview_date=entity.interview_date,
        )

    @staticmethod
    def _json_list(raw: str | None) -> list[object]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
            return value if isinstance(value, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

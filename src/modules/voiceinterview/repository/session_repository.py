from datetime import datetime

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import AsyncTaskStatus
from infrastructure.database.models import VoiceInterviewMessageORM, VoiceInterviewSessionORM
from modules.voiceinterview.model.voice_interview_dto import SessionMetaDTO
from modules.voiceinterview.model.voice_interview_entity import (
    InterviewPhase, VoiceInterviewSessionEntity, VoiceInterviewSessionStatus,
)


class VoiceInterviewSessionRepository:
    async def save(self, db: AsyncSession, entity: VoiceInterviewSessionEntity) -> VoiceInterviewSessionEntity:
        values = entity.model_dump(exclude={"id"}, by_alias=False)
        orm = VoiceInterviewSessionORM(**values)
        db.add(orm)
        await db.flush()
        return self._to_entity(orm)

    async def find_by_id(self, db: AsyncSession, session_id: int) -> VoiceInterviewSessionEntity | None:
        result = await db.execute(select(VoiceInterviewSessionORM).where(VoiceInterviewSessionORM.id == session_id))
        orm = result.scalar_one_or_none()
        return self._to_entity(orm) if orm is not None else None

    async def exists(self, db: AsyncSession, session_id: int) -> bool:
        result = await db.execute(select(VoiceInterviewSessionORM.id).where(VoiceInterviewSessionORM.id == session_id))
        return result.scalar_one_or_none() is not None

    async def update_fields(self, db: AsyncSession, session_id: int, **values: object) -> bool:
        values["updated_at"] = datetime.now()
        result = await db.execute(
            update(VoiceInterviewSessionORM).where(VoiceInterviewSessionORM.id == session_id).values(**values)
        )
        return bool(result.rowcount)

    async def delete(self, db: AsyncSession, session_id: int) -> bool:
        result = await db.execute(delete(VoiceInterviewSessionORM).where(VoiceInterviewSessionORM.id == session_id))
        return bool(result.rowcount)

    async def list_sessions(
        self, db: AsyncSession, user_id: str | None = None, status: VoiceInterviewSessionStatus | None = None
    ) -> list[SessionMetaDTO]:
        message_count = (
            select(func.count(VoiceInterviewMessageORM.id))
            .where(VoiceInterviewMessageORM.session_id == VoiceInterviewSessionORM.id)
            .where(VoiceInterviewMessageORM.message_type != "SUMMARY")
            .correlate(VoiceInterviewSessionORM).scalar_subquery()
        )
        stmt = select(VoiceInterviewSessionORM, message_count.label("message_count"))
        # userId has no authorization semantics. If supplied it remains a compatibility filter.
        if user_id is not None and user_id.strip():
            stmt = stmt.where(VoiceInterviewSessionORM.user_id == user_id.strip())
        if status is not None:
            stmt = stmt.where(VoiceInterviewSessionORM.status == status)
        rows = (await db.execute(stmt.order_by(desc(VoiceInterviewSessionORM.created_at)))).all()
        return [SessionMetaDTO(
            session_id=item.id, user_id=item.user_id, role_type=item.role_type,
            skill_id=item.skill_id, difficulty=item.difficulty, status=item.status.value,
            current_phase=item.current_phase.value, created_at=item.created_at, updated_at=item.updated_at,
            actual_duration=item.actual_duration, message_count=int(count or 0),
            evaluate_status=item.evaluate_status.value if item.evaluate_status else None,
            evaluate_error=item.evaluate_error,
        ) for item, count in rows]

    async def claim_evaluation(self, db: AsyncSession, session_id: int) -> bool:
        result = await db.execute(
            update(VoiceInterviewSessionORM)
            .where(VoiceInterviewSessionORM.id == session_id)
            .where(VoiceInterviewSessionORM.evaluate_status.in_([AsyncTaskStatus.PENDING, AsyncTaskStatus.FAILED]))
            .values(evaluate_status=AsyncTaskStatus.PROCESSING, evaluate_error=None, updated_at=datetime.now())
        )
        return bool(result.rowcount)

    async def finish_evaluation_claim(
        self,
        db: AsyncSession,
        session_id: int,
        claim_updated_at: datetime,
        status: AsyncTaskStatus,
        error: str | None = None,
    ) -> bool:
        """Finish only the worker generation represented by claim_updated_at."""
        result = await db.execute(
            update(VoiceInterviewSessionORM)
            .where(VoiceInterviewSessionORM.id == session_id)
            .where(VoiceInterviewSessionORM.evaluate_status == AsyncTaskStatus.PROCESSING)
            .where(VoiceInterviewSessionORM.updated_at == claim_updated_at)
            .values(
                evaluate_status=status,
                evaluate_error=error,
                updated_at=datetime.now(),
            )
        )
        return bool(result.rowcount)

    async def list_stale_evaluations(
        self, db: AsyncSession, status: AsyncTaskStatus, before: datetime
    ) -> list[int]:
        result = await db.execute(
            select(VoiceInterviewSessionORM.id)
            .where(VoiceInterviewSessionORM.evaluate_status == status)
            .where(VoiceInterviewSessionORM.updated_at < before)
        )
        return list(result.scalars().all())

    @staticmethod
    def _to_entity(orm: VoiceInterviewSessionORM) -> VoiceInterviewSessionEntity:
        return VoiceInterviewSessionEntity(
            id=orm.id, user_id=orm.user_id, role_type=orm.role_type, skill_id=orm.skill_id,
            difficulty=orm.difficulty, custom_jd_text=orm.custom_jd_text, resume_id=orm.resume_id,
            intro_enabled=orm.intro_enabled, tech_enabled=orm.tech_enabled,
            project_enabled=orm.project_enabled, hr_enabled=orm.hr_enabled,
            llm_provider=orm.llm_provider, current_phase=InterviewPhase(orm.current_phase.value),
            status=VoiceInterviewSessionStatus(orm.status.value), planned_duration=orm.planned_duration,
            actual_duration=orm.actual_duration, total_paused_seconds=orm.total_paused_seconds,
            start_time=orm.start_time, end_time=orm.end_time, paused_at=orm.paused_at,
            resumed_at=orm.resumed_at, evaluate_status=orm.evaluate_status,
            evaluate_error=orm.evaluate_error, created_at=orm.created_at, updated_at=orm.updated_at,
        )

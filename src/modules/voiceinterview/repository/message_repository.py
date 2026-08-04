from datetime import datetime

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import VoiceInterviewMessageORM, VoiceInterviewSessionORM
from modules.voiceinterview.model.voice_interview_dto import VoiceInterviewMessageDTO
from modules.voiceinterview.model.voice_interview_entity import (
    InterviewPhase, VoiceInterviewMessageEntity, VoiceMessageType,
)


class VoiceInterviewMessageRepository:
    async def list_for_context(self, db: AsyncSession, session_id: int) -> list[VoiceInterviewMessageEntity]:
        result = await db.execute(
            select(VoiceInterviewMessageORM)
            .where(VoiceInterviewMessageORM.session_id == session_id)
            .where(VoiceInterviewMessageORM.message_type != VoiceMessageType.SUMMARY)
            .order_by(VoiceInterviewMessageORM.sequence_num)
        )
        return [self._to_entity(item) for item in result.scalars().all()]

    async def list_public(self, db: AsyncSession, session_id: int) -> list[VoiceInterviewMessageDTO]:
        return [VoiceInterviewMessageDTO(
            id=item.id or 0, session_id=item.session_id, message_type=item.message_type.value,
            phase=item.phase.value if item.phase else None, user_recognized_text=item.user_recognized_text,
            ai_generated_text=item.ai_generated_text, sequence_num=item.sequence_num, timestamp=item.timestamp,
        ) for item in await self.list_for_context(db, session_id)]

    async def get_latest_summary(self, db: AsyncSession, session_id: int) -> VoiceInterviewMessageEntity | None:
        result = await db.execute(
            select(VoiceInterviewMessageORM)
            .where(VoiceInterviewMessageORM.session_id == session_id)
            .where(VoiceInterviewMessageORM.message_type == VoiceMessageType.SUMMARY)
            .order_by(desc(VoiceInterviewMessageORM.summary_covered_sequence), desc(VoiceInterviewMessageORM.id))
            .limit(1)
        )
        item = result.scalar_one_or_none()
        return self._to_entity(item) if item else None

    async def save_summary(
        self, db: AsyncSession, session_id: int, text: str, covered_sequence: int
    ) -> VoiceInterviewMessageEntity:
        entity = VoiceInterviewMessageEntity(
            session_id=session_id, message_type=VoiceMessageType.SUMMARY,
            ai_generated_text=text.strip(), sequence_num=await self._next_sequence(db, session_id),
            summary_covered_sequence=covered_sequence,
        )
        return await self.save(db, entity)

    async def fill_latest_unanswered(self, db: AsyncSession, session_id: int, user_text: str) -> bool:
        result = await db.execute(
            select(VoiceInterviewMessageORM.id)
            .where(VoiceInterviewMessageORM.session_id == session_id)
            .where(VoiceInterviewMessageORM.message_type == VoiceMessageType.AI_SPEECH)
            .where(VoiceInterviewMessageORM.user_recognized_text.is_(None))
            .order_by(desc(VoiceInterviewMessageORM.sequence_num)).limit(1)
        )
        message_id = result.scalar_one_or_none()
        if message_id is None:
            return False
        updated = await db.execute(
            update(VoiceInterviewMessageORM).where(VoiceInterviewMessageORM.id == message_id)
            .where(VoiceInterviewMessageORM.user_recognized_text.is_(None))
            .values(user_recognized_text=user_text.strip())
        )
        return bool(updated.rowcount)

    async def append_ai_question(
        self, db: AsyncSession, session_id: int, phase: InterviewPhase | str, text: str
    ) -> VoiceInterviewMessageEntity:
        phase_value = phase if isinstance(phase, InterviewPhase) else InterviewPhase(phase.upper())
        return await self.save(db, VoiceInterviewMessageEntity(
            session_id=session_id, message_type=VoiceMessageType.AI_SPEECH, phase=phase_value,
            ai_generated_text=text.strip(), sequence_num=await self._next_sequence(db, session_id),
        ))

    async def save(self, db: AsyncSession, entity: VoiceInterviewMessageEntity) -> VoiceInterviewMessageEntity:
        orm = VoiceInterviewMessageORM(**entity.model_dump(exclude={"id"}, by_alias=False))
        db.add(orm)
        await db.flush()
        return self._to_entity(orm)

    async def _next_sequence(self, db: AsyncSession, session_id: int) -> int:
        # Serialize sequence allocation per session. MySQL honors FOR UPDATE;
        # SQLite test databases safely ignore it.
        await db.execute(
            select(VoiceInterviewSessionORM.id)
            .where(VoiceInterviewSessionORM.id == session_id)
            .with_for_update()
        )
        result = await db.execute(
            select(func.coalesce(func.max(VoiceInterviewMessageORM.sequence_num), 0))
            .where(VoiceInterviewMessageORM.session_id == session_id)
        )
        return int(result.scalar_one()) + 1

    @staticmethod
    def _to_entity(orm: VoiceInterviewMessageORM) -> VoiceInterviewMessageEntity:
        return VoiceInterviewMessageEntity(
            id=orm.id, session_id=orm.session_id, message_type=VoiceMessageType(orm.message_type.value),
            phase=InterviewPhase(orm.phase.value) if orm.phase else None,
            user_recognized_text=orm.user_recognized_text, ai_generated_text=orm.ai_generated_text,
            sequence_num=orm.sequence_num, summary_covered_sequence=orm.summary_covered_sequence,
            timestamp=orm.timestamp, created_at=orm.created_at,
        )

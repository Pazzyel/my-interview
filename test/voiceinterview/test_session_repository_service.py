import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from infrastructure.database.models import (
    Base, VoiceInterviewEvaluationORM, VoiceInterviewMessageORM,
)
from modules.voiceinterview.model.voice_interview_dto import CreateVoiceInterviewRequest
from modules.voiceinterview.model.voice_interview_entity import InterviewPhase
from modules.voiceinterview.repository.message_repository import VoiceInterviewMessageRepository
from modules.voiceinterview.service.session_service import VoiceInterviewSessionService


@asynccontextmanager
async def database(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def test_user_id_default_lifecycle_and_publish_after_commit(tmp_path):
    async def scenario():
        async with database(tmp_path / "lifecycle.db") as db:
            published = []

            async def publish(session_id: int):
                # A SELECT after service commit must see COMPLETED/PENDING.
                entity = await service.get_session(db, session_id)
                published.append((session_id, entity.status.value, entity.evaluate_status.value))

            service = VoiceInterviewSessionService(evaluation_publisher=publish)
            response = await service.create_session(
                db, CreateVoiceInterviewRequest(userId="  ", skillId="python-backend"),
                "ws://test/ws/voice-interview/{session_id}",
            )
            assert response.user_id == "default"
            assert response.current_phase == "TECH"

            await service.pause_session(db, response.session_id)
            await service.sessions.update_fields(
                db, response.session_id, paused_at=datetime.now() - timedelta(seconds=5)
            )
            await db.commit()
            await service.resume_session(db, response.session_id, "ws://test/{session_id}")
            resumed = await service.get_session(db, response.session_id)
            assert resumed.total_paused_seconds >= 5

            await service.end_session(db, response.session_id)
            assert published == [(response.session_id, "COMPLETED", "PENDING")]
    asyncio.run(scenario())


def test_messages_summary_filter_and_database_cascade(tmp_path):
    async def scenario():
        async with database(tmp_path / "cascade.db") as db:
            service = VoiceInterviewSessionService()
            response = await service.create_session(
                db, CreateVoiceInterviewRequest(userId=None), "ws://test/{session_id}"
            )
            messages = VoiceInterviewMessageRepository()
            question = await messages.append_ai_question(db, response.session_id, InterviewPhase.TECH, "Explain asyncio")
            assert await messages.fill_latest_unanswered(db, response.session_id, "It is cooperative concurrency")
            await messages.save_summary(db, response.session_id, "Discussed asyncio", question.sequence_num)
            db.add(VoiceInterviewEvaluationORM(session_id=response.session_id, overall_score=90))
            await db.commit()

            public = await service.get_messages(db, response.session_id)
            assert len(public) == 1
            assert public[0].user_recognized_text == "It is cooperative concurrency"

            await service.delete_session(db, response.session_id)
            assert (await db.scalar(select(func.count()).select_from(VoiceInterviewMessageORM))) == 0
            assert (await db.scalar(select(func.count()).select_from(VoiceInterviewEvaluationORM))) == 0
    asyncio.run(scenario())

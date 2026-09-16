import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modules.knowledgebase.model.rag_chat_message_entity import RagChatSessionEntity
from modules.knowledgebase.model.rag_chat_session_dto import CreateSessionRequest
from modules.knowledgebase.service.rag_chat_session_service import RagChatSessionService


def test_create_session_commits_before_returning_id() -> None:
    async def scenario() -> None:
        now = datetime.now()
        session_entity = RagChatSessionEntity(1, "Knowledge", "ACTIVE", now, now, 0, False, [])
        repository = SimpleNamespace(
            count_knowledge_bases_by_ids=AsyncMock(return_value=1),
            get_knowledge_bases_by_ids=AsyncMock(return_value=[SimpleNamespace(name="Knowledge")]),
            create_session=AsyncMock(return_value=session_entity),
        )
        db = AsyncMock()
        service = RagChatSessionService(repository, AsyncMock())

        result = await service.create_session(db, CreateSessionRequest(knowledgeBaseIds=[2]))

        assert result.id == 1
        db.commit.assert_awaited_once()

    asyncio.run(scenario())


def test_stream_message_writes_are_committed_during_stream() -> None:
    async def scenario() -> None:
        repository = SimpleNamespace(
            prepare_stream_messages=AsyncMock(return_value=9),
            complete_stream_message=AsyncMock(return_value=True),
        )
        db = AsyncMock()
        service = RagChatSessionService(repository, AsyncMock())

        message_id = await service.prepare_stream_message(db, 1, "question")
        await service.complete_stream_message(db, message_id, "answer")

        assert message_id == 9
        assert db.commit.await_count == 2

    asyncio.run(scenario())

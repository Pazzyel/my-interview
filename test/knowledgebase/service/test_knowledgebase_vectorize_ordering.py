import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import UploadFile

from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from modules.knowledgebase.service import knowledgebase_upload_service as upload_module
from modules.knowledgebase.service.knowledgebase_upload_service import KnowledgeBaseUploadService
from modules.knowledgebase.service import knowledgebase_vectorize_consumer_service as consumer_module


def _upload_file() -> UploadFile:
    return UploadFile(
        filename="knowledge.md",
        file=BytesIO(b"# Knowledge"),
        headers={"content-type": "text/markdown"},
        size=11,
    )


def _saved_entity() -> KnowledgeBaseEntity:
    return KnowledgeBaseEntity(
        id=7,
        file_hash="hash",
        name="Knowledge",
        original_filename="knowledge.md",
        file_size=11,
        content_type="text/markdown",
        storage_key="knowledgebase/knowledge.md",
        storage_url="https://storage/knowledge.md",
        vector_status=VectorStatus.PENDING,
    )


def test_knowledge_base_is_committed_before_vectorize_message_is_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_module.app_config, "kb_max_file_size_bytes", 50 * 1024 * 1024, raising=False)
    monkeypatch.setattr(upload_module.app_config, "kb_allowed_types", ["text/markdown"], raising=False)
    events: list[str] = []
    db = AsyncMock()

    async def commit() -> None:
        events.append("commit")

    db.commit.side_effect = commit

    async def save(*_args) -> KnowledgeBaseEntity:
        events.append("save")
        return _saved_entity()

    def publish(*_args) -> None:
        events.append("publish")

    service = KnowledgeBaseUploadService(
        parse_service=SimpleNamespace(
            detect_content_type=Mock(return_value="text/markdown"),
            parse_content=AsyncMock(return_value="Knowledge content"),
        ),
        persistence_service=SimpleNamespace(save_knowledge_base=AsyncMock(side_effect=save)),
        storage_service=SimpleNamespace(
            upload_knowledgebase=AsyncMock(return_value="knowledgebase/knowledge.md"),
            get_file_url=AsyncMock(return_value="https://storage/knowledge.md"),
        ),
        knowledge_base_repository=SimpleNamespace(find_by_file_hash=AsyncMock(return_value=None)),
        file_validation_service=SimpleNamespace(
            validate_file=AsyncMock(return_value=11),
            validate_content_type_by_list=Mock(),
        ),
        file_hash_service=SimpleNamespace(calculate_hash_file=AsyncMock(return_value="hash")),
        vectorize_stream_producer=SimpleNamespace(send_vectorize_task=Mock(side_effect=publish)),
    )

    asyncio.run(service.upload_knowledge_base(db, _upload_file()))

    assert events == ["save", "commit", "publish"]


class _Session:
    def __init__(self) -> None:
        self.rollback = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None


def test_missing_knowledge_base_causes_message_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session()
    monkeypatch.setattr(consumer_module, "async_session_factory", lambda: session)
    repository = SimpleNamespace(find_by_id=AsyncMock(return_value=None))
    vector_service = SimpleNamespace(vectorize_and_store=AsyncMock())
    service = consumer_module.KnowledgeBaseVectorizeConsumerService(repository, vector_service)

    with pytest.raises(RuntimeError, match="not visible"):
        asyncio.run(service.process_task(7, "content", "Knowledge", None))

    session.rollback.assert_awaited_once()
    vector_service.vectorize_and_store.assert_not_awaited()

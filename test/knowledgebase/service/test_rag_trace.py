import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from modules.knowledgebase.model.rag_trace import RagRunMode, RagTrace, RagTraceStatus
from modules.knowledgebase.service.knowledgebase_chunking_service import KnowledgeBaseChunkingService
from modules.knowledgebase.service.rag_trace_recorder import RagTraceRecorder


class FailingTraceRepository:
    async def create(self, trace):
        raise RuntimeError("trace db unavailable")

    async def append_event(self, *args, **kwargs):
        raise RuntimeError("trace db unavailable")

    async def finish(self, trace):
        raise RuntimeError("trace db unavailable")


def _trace(trace_id: str) -> RagTrace:
    return RagTrace(
        trace_id=trace_id,
        original_query="Redis 为什么快？",
        knowledge_base_ids=[1],
        run_mode=RagRunMode.ONLINE,
        started_at=datetime.now(),
    )


def test_chunk_ids_are_stable_and_change_with_content() -> None:
    service = KnowledgeBaseChunkingService()

    first = service.split("第一段知识。", 7, "知识库", "后端")
    second = service.split("第一段知识。", 7, "知识库", "后端")
    changed = service.split("第二段知识。", 7, "知识库", "后端")

    assert first[0].metadata["chunk_id"] == second[0].metadata["chunk_id"]
    assert first[0].metadata["chunk_id"] != changed[0].metadata["chunk_id"]
    assert first[0].metadata["chunk_index"] == 0


def test_online_trace_persistence_failure_is_best_effort() -> None:
    async def scenario() -> None:
        recorder = RagTraceRecorder(FailingTraceRepository())
        await recorder.start(_trace("online"), required=False)
        result = await recorder.finish("online", RagTraceStatus.COMPLETED, "回答")
        assert result.response == "回答"

    asyncio.run(scenario())


def test_required_trace_persistence_failure_is_raised() -> None:
    async def scenario() -> None:
        recorder = RagTraceRecorder(FailingTraceRepository())
        with pytest.raises(RuntimeError, match="trace db unavailable"):
            await recorder.start(_trace("evaluation"), required=True)

    asyncio.run(scenario())


def test_record_usage_false_skips_knowledge_base_counter() -> None:
    from modules.knowledgebase.service.knowledgebase_query_service import (
        KnowledgeBaseQueryService,
        KnowledgeQueryState,
    )

    async def scenario() -> None:
        counter = AsyncMock()
        resolver = AsyncMock()
        resolver.resolve.return_value = object()
        recorder = RagTraceRecorder()
        await recorder.start(_trace("no-count"), required=False)
        service = KnowledgeBaseQueryService(
            AsyncMock(), AsyncMock(), counter, resolver, recorder
        )
        state = KnowledgeQueryState(
            trace_id="no-count",
            origin_query="Redis",
            knowledgebase_ids=[1],
            record_usage=False,
        )

        await service.pre_retrieve(state, {})

        counter.update_question_counts.assert_not_awaited()

    asyncio.run(scenario())

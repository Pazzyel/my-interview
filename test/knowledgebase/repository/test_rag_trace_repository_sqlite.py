import asyncio
from datetime import datetime

from knowledgebase_repository_mocks import InMemorySqliteSessionFactory

from modules.knowledgebase.model.rag_trace import RagRunMode, RagTrace, RagTraceStatus
from modules.knowledgebase.repository.rag_trace_repository import RagTraceRepository
from modules.knowledgebase.service.rag_trace_recorder import RagTraceRecorder


def test_trace_run_and_events_can_be_reconstructed() -> None:
    async def scenario() -> None:
        factory = InMemorySqliteSessionFactory()
        await factory.init()
        try:
            repository = RagTraceRepository(factory.session)
            recorder = RagTraceRecorder(repository)
            trace = RagTrace(
                trace_id="trace-1",
                original_query="什么是 Redis？",
                knowledge_base_ids=[3],
                run_mode=RagRunMode.EVALUATION,
                started_at=datetime.now(),
            )
            await recorder.start(trace, required=True)
            await recorder.event("trace-1", "query_rewritten", "pre_retrieve", {
                "rewritten_query": "Redis 定义",
                "candidate_queries": ["Redis 定义", "什么是 Redis？"],
            })
            await recorder.event("trace-1", "retrieval_completed", "vector_retrieve", {
                "query": "Redis 定义",
                "top_k": 5,
                "min_score": 0.3,
                "latency_ms": 12.5,
                "hits": [{
                    "chunk_id": "3:0:abc",
                    "content": "Redis 是内存数据库。",
                    "score": 0.91,
                    "rank": 1,
                    "metadata": {"kb_id": "3"},
                }],
            })
            await recorder.event("trace-1", "context_selected", "vector_retrieve", {
                "selected_query": "Redis 定义",
                "chunk_ids": ["3:0:abc"],
            })
            await recorder.finish("trace-1", RagTraceStatus.COMPLETED, "Redis 是内存数据库。")

            restored = await repository.get("trace-1")
            assert restored is not None
            assert restored.status == RagTraceStatus.COMPLETED
            assert restored.rewritten_query == "Redis 定义"
            assert restored.selected_query == "Redis 定义"
            assert restored.selected_contexts[0].score == 0.91
            assert restored.response == "Redis 是内存数据库。"
        finally:
            await factory.dispose()

    asyncio.run(scenario())

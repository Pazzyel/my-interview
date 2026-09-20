from datetime import datetime

from evaluation.ragas_cli import build_evaluation_row
from modules.knowledgebase.model.rag_trace import (
    RagRetrievalHit,
    RagRunMode,
    RagRunResult,
    RagTrace,
)


def test_ragas_adapter_maps_trace_fields() -> None:
    trace = RagTrace(
        trace_id="trace-1",
        original_query="问题",
        knowledge_base_ids=[1],
        run_mode=RagRunMode.EVALUATION,
        started_at=datetime.now(),
        selected_contexts=[
            RagRetrievalHit(chunk_id="1:0:abc", content="上下文", score=0.9, rank=1)
        ],
    )
    result = RagRunResult(answer="回答", trace=trace)

    row = build_evaluation_row({
        "user_input": "问题",
        "reference": "标准答案",
        "reference_contexts": ["标准上下文"],
    }, result)

    assert row == {
        "user_input": "问题",
        "retrieved_contexts": ["上下文"],
        "response": "回答",
        "reference": "标准答案",
        "reference_contexts": ["标准上下文"],
    }

import asyncio
import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from infrastructure.vector.milvus_vector_service import MilvusVectorService
from infrastructure.vector.vector_service import VectorService


class FakeStore:
    def __init__(self) -> None:
        self.aadd_documents = AsyncMock()
        self.adelete = AsyncMock(return_value=True)
        self.asimilarity_search = AsyncMock(return_value=[])
        self.asimilarity_search_with_score = AsyncMock(return_value=[])
        self.similarity_search_with_score = MagicMock(return_value=[])
        self.retriever = MagicMock()
        self.as_retriever = MagicMock(return_value=self.retriever)


def run(coro):
    return asyncio.run(coro)


def test_implements_vector_service_protocol_and_delegates_store_operations():
    store = FakeStore()
    service = MilvusVectorService(store=store)
    documents = [Document(page_content="content")]

    assert isinstance(service, VectorService)
    run(service.add_documents(documents))
    retriever = run(service.get_retriever("similarity", {"k": 3}))

    store.aadd_documents.assert_awaited_once_with(documents)
    store.as_retriever.assert_called_once_with(
        search_type="similarity",
        search_kwargs={"k": 3},
    )
    assert retriever is store.retriever


def test_threshold_retriever_filters_multi_vector_scores():
    expected = Document(page_content="match")
    store = FakeStore()
    store.asimilarity_search_with_score.return_value = [
        (expected, 0.8),
        (Document(page_content="below threshold"), 0.2),
    ]
    service = MilvusVectorService(store=store)

    retriever = run(service.get_retriever(search_kwargs={"k": 2, "score_threshold": 0.5}))
    result = run(retriever.ainvoke("query"))

    assert result == [expected]
    store.asimilarity_search_with_score.assert_awaited_once_with(
        query="query",
        k=2,
        ranker_type="weighted",
        ranker_params={"weights": [1.0, 0.0]},
    )


def test_dependency_module_wires_milvus_as_default_implementation():
    dependencies_path = Path(__file__).resolve().parents[3] / "src/common/dependencies.py"
    tree = ast.parse(dependencies_path.read_text(encoding="utf-8"))

    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "vector_service"
            for target in node.targets
        )
    ]

    assert len(assignments) == 1
    value = assignments[0].value
    assert isinstance(value, ast.Call)
    assert isinstance(value.func, ast.Name)
    assert value.func.id == "MilvusVectorService"


def test_similar_search_applies_native_filter_and_threshold():
    expected = Document(page_content="match", metadata={"kb_id": "7"})
    store = FakeStore()
    store.asimilarity_search_with_score.return_value = [
        (expected, 0.91),
        (Document(page_content="below threshold"), 0.20),
    ]
    service = MilvusVectorService(store=store)

    result = run(service.similar_search("query", [7, 8], 2, 0.25))

    assert result == [expected]
    store.asimilarity_search_with_score.assert_awaited_once_with(
        query="query",
        k=2,
        expr='kb_id in ["7", "8"]',
        ranker_type="weighted",
        ranker_params={"weights": [1.0, 0.0]},
    )


def test_similar_search_without_kb_ids_omits_filter_expression():
    store = FakeStore()
    service = MilvusVectorService(store=store)

    run(service.similar_search("query", [], 3, 0.2))

    assert store.asimilarity_search_with_score.await_args.kwargs["expr"] is None


def test_rrf_uses_milvus_hybrid_ranker_and_shared_filter():
    expected = [Document(page_content="hybrid match")]
    store = FakeStore()
    store.asimilarity_search.return_value = expected
    service = MilvusVectorService(store=store)

    result = run(service.similar_search_rrf("hybrid query", [1, 2], 5))

    assert result == expected
    store.asimilarity_search.assert_awaited_once_with(
        query="hybrid query",
        k=5,
        expr='kb_id in ["1", "2"]',
        ranker_type="rrf",
        ranker_params={"k": 60},
    )


def test_delete_by_kb_id_uses_milvus_expression():
    store = FakeStore()
    service = MilvusVectorService(store=store)

    run(service.delete_by_kb_id(42))

    store.adelete.assert_awaited_once_with(expr='kb_id == "42"')


def test_delete_by_kb_id_raises_when_milvus_reports_failure():
    store = FakeStore()
    store.adelete.return_value = False
    service = MilvusVectorService(store=store)

    with pytest.raises(RuntimeError, match="Milvus failed to delete"):
        run(service.delete_by_kb_id(42))


@pytest.mark.parametrize("method_name", ["similar_search", "similar_search_rrf"])
def test_non_positive_top_k_returns_empty_without_calling_milvus(method_name):
    store = FakeStore()
    service = MilvusVectorService(store=store)

    if method_name == "similar_search":
        result = run(service.similar_search("query", [], 0, 0.2))
    else:
        result = run(service.similar_search_rrf("query", [], 0))

    assert result == []
    store.asimilarity_search.assert_not_awaited()
    store.asimilarity_search_with_score.assert_not_awaited()

import asyncio
import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from common.config import app_config
from infrastructure.vector.elasticsearch_vector_service import ElasticsearchVectorService
from infrastructure.vector.vector_service import VectorService


class FakeStore:
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.embedding = MagicMock()
        self.embedding.aembed_query = AsyncMock(return_value=[0.1, 0.2])
        self.client = MagicMock()
        self.client.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "text": "second-ranked-by-source",
                                "metadata": {"kb_id": "2"},
                            }
                        },
                        {
                            "_source": {
                                "text": "first-ranked-by-source",
                                "metadata": {"kb_id": "1"},
                            }
                        },
                    ]
                }
            }
        )
        self.client.delete_by_query = AsyncMock()
        self.aadd_documents = AsyncMock()
        self.retriever = MagicMock()
        self.retriever.ainvoke = AsyncMock(return_value=documents or [])
        self.as_retriever = MagicMock(return_value=self.retriever)


def run(coro):
    return asyncio.run(coro)


def test_implements_vector_service_protocol_and_delegates_store_operations():
    store = FakeStore()
    service = ElasticsearchVectorService(store=store)
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


def test_dependency_module_wires_elasticsearch_as_default_implementation():
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
    assert value.func.id == "ElasticsearchVectorService"


def test_similar_search_applies_native_filter_and_threshold():
    expected = [Document(page_content="match", metadata={"kb_id": "7"})]
    store = FakeStore(expected)
    service = ElasticsearchVectorService(store=store)

    result = run(service.similar_search("query", [7, 8], 2, 0.25))

    assert result == expected
    store.as_retriever.assert_called_once_with(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": 2,
            "score_threshold": 0.25,
            "filter": [
                {"terms": {"metadata.kb_id.keyword": ["7", "8"]}}
            ],
        },
    )


def test_similar_search_falls_back_and_filters_locally():
    native_retriever = MagicMock()
    native_retriever.ainvoke = AsyncMock(side_effect=RuntimeError("bad filter"))
    fallback_retriever = MagicMock()
    fallback_retriever.ainvoke = AsyncMock(
        return_value=[
            Document(page_content="keep", metadata={"kb_id": 7}),
            Document(page_content="drop", metadata={"kb_id": "9"}),
        ]
    )
    store = FakeStore()
    store.as_retriever.side_effect = [native_retriever, fallback_retriever]
    service = ElasticsearchVectorService(store=store)

    result = run(service.similar_search("query", [7], 2, 0.25))

    assert [document.page_content for document in result] == ["keep"]
    assert store.as_retriever.call_count == 2
    assert store.as_retriever.call_args_list[1].kwargs == {
        "search_type": "similarity_score_threshold",
        "search_kwargs": {"k": 6, "score_threshold": 0.25},
    }


def test_delete_by_kb_id_uses_elasticsearch_delete_by_query():
    store = FakeStore()
    service = ElasticsearchVectorService(store=store)

    run(service.delete_by_kb_id(42))

    store.client.delete_by_query.assert_awaited_once_with(
        index=app_config.elasticsearch_index_name,
        body={
            "query": {
                "term": {"metadata.kb_id.keyword": "42"},
            }
        },
        refresh=True,
    )


def test_rrf_uses_native_standard_and_knn_retrievers_with_shared_filter():
    store = FakeStore()
    service = ElasticsearchVectorService(store=store)

    result = run(service.similar_search_rrf("hybrid query", [1, 2], 5))

    store.embedding.aembed_query.assert_awaited_once_with("hybrid query")
    call = store.client.search.await_args.kwargs
    assert call["index"] == app_config.elasticsearch_index_name
    assert call["size"] == 5
    assert call["source_includes"] == ["text", "metadata"]
    rrf = call["retriever"]["rrf"]
    assert "rank_constant" not in rrf
    assert rrf["rank_window_size"] == 5
    assert rrf["retrievers"] == [
        {
            "standard": {
                "query": {
                    "bool": {
                        "must": [{"match": {"text": "hybrid query"}}],
                        "filter": [
                            {
                                "terms": {
                                    "metadata.kb_id.keyword": ["1", "2"]
                                }
                            }
                        ],
                    }
                }
            }
        },
        {
            "knn": {
                "field": "vector",
                "query_vector": [0.1, 0.2],
                "k": 5,
                "num_candidates": 50,
                "filter": [
                    {"terms": {"metadata.kb_id.keyword": ["1", "2"]}}
                ],
            }
        },
    ]
    assert [document.page_content for document in result] == [
        "second-ranked-by-source",
        "first-ranked-by-source",
    ]


def test_rrf_without_kb_ids_omits_filters():
    store = FakeStore()
    service = ElasticsearchVectorService(store=store)

    run(service.similar_search_rrf("query", [], 3))

    retrievers = store.client.search.await_args.kwargs["retriever"]["rrf"][
        "retrievers"
    ]
    assert retrievers[0] == {"standard": {"query": {"match": {"text": "query"}}}}
    assert "filter" not in retrievers[1]["knn"]


@pytest.mark.parametrize("method_name", ["similar_search", "similar_search_rrf"])
def test_non_positive_top_k_returns_empty_without_calling_elasticsearch(method_name):
    store = FakeStore()
    service = ElasticsearchVectorService(store=store)

    if method_name == "similar_search":
        result = run(service.similar_search("query", [], 0, 0.2))
    else:
        result = run(service.similar_search_rrf("query", [], 0))

    assert result == []
    store.as_retriever.assert_not_called()
    store.client.search.assert_not_awaited()


def test_rrf_propagates_embedding_and_elasticsearch_errors():
    embedding_error_store = FakeStore()
    embedding_error_store.embedding.aembed_query.side_effect = RuntimeError("embedding")
    with pytest.raises(RuntimeError, match="embedding"):
        run(
            ElasticsearchVectorService(
                store=embedding_error_store
            ).similar_search_rrf("query", [], 3)
        )

    search_error_store = FakeStore()
    search_error_store.client.search.side_effect = RuntimeError("elasticsearch")
    with pytest.raises(RuntimeError, match="elasticsearch"):
        run(
            ElasticsearchVectorService(
                store=search_error_store
            ).similar_search_rrf("query", [], 3)
        )

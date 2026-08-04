import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_elasticsearch import AsyncDenseVectorStrategy, AsyncElasticsearchStore

from common.config import app_config
from common.llm_provider import LlmProviderRegistry

logger = logging.getLogger(__name__)

_TEXT_FIELD = "text"
_VECTOR_FIELD = "vector"
_METADATA_FIELD = "metadata"
_MAX_KNN_CANDIDATES = 10_000


class ElasticsearchVectorService:
    """Elasticsearch-backed implementation of the vector service contract."""

    def __init__(
        self,
        store: AsyncElasticsearchStore | None = None,
        registry: LlmProviderRegistry | None = None,
    ) -> None:
        self._store = store
        self._registry = registry or LlmProviderRegistry()
        self._embedding_identity: int | None = None

    async def _current_store(self) -> AsyncElasticsearchStore:
        if self._store is not None and self._embedding_identity is None:
            return self._store

        embedding = await self._registry.get_default_embedding_model()
        if self._store is None or self._embedding_identity != id(embedding):
            self._store = AsyncElasticsearchStore(
                es_url=app_config.elasticsearch_url,
                index_name=app_config.elasticsearch_index_name,
                embedding=embedding,
                strategy=AsyncDenseVectorStrategy(),
            )
            self._embedding_identity = id(embedding)
        return self._store

    async def add_documents(self, documents: list[Document]) -> None:
        await (await self._current_store()).aadd_documents(documents)

    async def get_retriever(
        self,
        search_type: str = "similarity_score_threshold",
        search_kwargs: dict[str, Any] | None = None,
    ) -> BaseRetriever:
        return (await self._current_store()).as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs,
        )

    async def similar_search(
        self,
        query: str,
        knowledgebase_ids: list[int],
        top_k: int,
        min_score: float,
    ) -> list[Document]:
        if top_k <= 0:
            return []

        try:
            store = await self._current_store()
            pre_filter = self._build_kb_filter(knowledgebase_ids)
            search_kwargs: dict[str, Any] = {
                "k": top_k,
                "score_threshold": min_score,
            }
            if pre_filter:
                search_kwargs["filter"] = pre_filter

            retriever = store.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs=search_kwargs,
            )
            documents = await retriever.ainvoke(query)
            return documents[:top_k]
        except Exception as exc:
            logger.warning(
                "Vector search pre-filter failed; falling back to local filtering: %s",
                str(exc),
            )
            return await self._similar_search_fallback(
                query,
                knowledgebase_ids,
                top_k,
                min_score,
            )

    async def similar_search_rrf(
        self,
        query: str,
        knowledgebase_ids: list[int],
        top_k: int,
    ) -> list[Document]:
        if top_k <= 0:
            return []
        if top_k > _MAX_KNN_CANDIDATES:
            raise ValueError(f"top_k must be <= {_MAX_KNN_CANDIDATES}")

        store = await self._current_store()
        embedding = store.embedding
        if embedding is None:
            raise RuntimeError("Elasticsearch vector store has no embedding model")
        query_vector = await embedding.aembed_query(query)

        filters = self._build_kb_filter(knowledgebase_ids)
        standard_query: dict[str, Any] = {"match": {_TEXT_FIELD: query}}
        if filters:
            standard_query = {
                "bool": {
                    "must": [standard_query],
                    "filter": filters,
                }
            }

        knn_retriever: dict[str, Any] = {
            "field": _VECTOR_FIELD,
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": min(max(top_k, 50), _MAX_KNN_CANDIDATES),
        }
        if filters:
            knn_retriever["filter"] = filters

        response = await store.client.search(
            index=app_config.elasticsearch_index_name,
            retriever={
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": standard_query}},
                        {"knn": knn_retriever},
                    ],
                    "rank_window_size": top_k,
                }
            },
            size=top_k,
            source_includes=[_TEXT_FIELD, _METADATA_FIELD],
        )

        return [self._hit_to_document(hit) for hit in response["hits"]["hits"]]

    async def delete_by_kb_id(self, knowledgebase_id: int) -> None:
        store = await self._current_store()
        await store.client.delete_by_query(
            index=app_config.elasticsearch_index_name,
            body={
                "query": {
                    "term": {
                        "metadata.kb_id.keyword": str(knowledgebase_id),
                    }
                }
            },
            refresh=True,
        )

    async def _similar_search_fallback(
        self,
        query: str,
        knowledgebase_ids: list[int],
        top_k: int,
        min_score: float,
    ) -> list[Document]:
        retriever = (await self._current_store()).as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "k": max(top_k * 3, top_k),
                "score_threshold": min_score,
            },
        )
        documents = await retriever.ainvoke(query)

        if knowledgebase_ids:
            kb_id_strs = {str(kid) for kid in knowledgebase_ids}
            documents = [
                document
                for document in documents
                if str(document.metadata.get("kb_id")) in kb_id_strs
            ]
        return documents[:top_k]

    @staticmethod
    def _build_kb_filter(knowledgebase_ids: list[int]) -> list[dict[str, Any]]:
        kb_id_strs = [str(kid) for kid in knowledgebase_ids if kid is not None]
        if not kb_id_strs:
            return []
        return [{"terms": {"metadata.kb_id.keyword": kb_id_strs}}]

    @staticmethod
    def _hit_to_document(hit: dict[str, Any]) -> Document:
        source = hit.get("_source", {})
        return Document(
            page_content=source.get(_TEXT_FIELD, ""),
            metadata=source.get(_METADATA_FIELD, {}),
        )

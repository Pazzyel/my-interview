import json
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_milvus import BM25BuiltInFunction, Milvus

from common.config import app_config
from common.llm_provider import LlmProviderRegistry

_DENSE_VECTOR_FIELD = "vector"
_SPARSE_VECTOR_FIELD = "sparse"
_RRF_RANK_CONSTANT = 60
_DENSE_ONLY_WEIGHTS = [1.0, 0.0]


class _MilvusThresholdRetriever(BaseRetriever):
    """Score-threshold retriever for a Milvus multi-vector collection."""

    store: Any
    search_kwargs: dict[str, Any]

    def _search_options(self) -> tuple[float, dict[str, Any]]:
        options = self.search_kwargs.copy()
        score_threshold = float(options.pop("score_threshold", 0.0))
        options.setdefault("ranker_type", "weighted")
        options.setdefault("ranker_params", {"weights": _DENSE_ONLY_WEIGHTS})
        return score_threshold, options

    def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        score_threshold, options = self._search_options()
        results = self.store.similarity_search_with_score(query=query, **options)
        return [document for document, score in results if score >= score_threshold]

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Any,
    ) -> list[Document]:
        score_threshold, options = self._search_options()
        results = await self.store.asimilarity_search_with_score(query=query, **options)
        return [document for document, score in results if score >= score_threshold]


class MilvusVectorService:
    """Milvus-backed implementation of the vector service contract."""

    def __init__(
        self,
        store: Milvus | None = None,
        registry: LlmProviderRegistry | None = None,
    ) -> None:
        self._store = store
        self._registry = registry or LlmProviderRegistry()
        self._embedding_identity: int | None = None

    async def _current_store(self) -> Milvus:
        if self._store is not None and self._embedding_identity is None:
            return self._store

        embedding = await self._registry.get_default_embedding_model()
        if self._store is None or self._embedding_identity != id(embedding):
            connection_args: dict[str, Any] = {"uri": app_config.milvus_uri}
            if app_config.milvus_token:
                connection_args["token"] = app_config.milvus_token

            self._store = Milvus(
                embedding_function=embedding,
                builtin_function=BM25BuiltInFunction(
                    output_field_names=_SPARSE_VECTOR_FIELD,
                ),
                vector_field=[_DENSE_VECTOR_FIELD, _SPARSE_VECTOR_FIELD],
                connection_args=connection_args,
                collection_name=app_config.milvus_collection_name,
                consistency_level=app_config.milvus_consistency_level,
                auto_id=True,
                enable_dynamic_field=True,
                index_params=[
                    {
                        "index_type": "AUTOINDEX",
                        "metric_type": "COSINE",
                        "params": {},
                    },
                    {
                        "index_type": "AUTOINDEX",
                        "metric_type": "BM25",
                        "params": {},
                    },
                ],
            )
            self._embedding_identity = id(embedding)
        return self._store

    async def add_documents(self, documents: list[Document]) -> None:
        if documents:
            await (await self._current_store()).aadd_documents(documents)

    async def get_retriever(
        self,
        search_type: str = "similarity_score_threshold",
        search_kwargs: dict[str, Any] | None = None,
    ) -> BaseRetriever:
        store = await self._current_store()
        if search_type == "similarity_score_threshold":
            return _MilvusThresholdRetriever(
                store=store,
                search_kwargs=search_kwargs or {},
            )
        return store.as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs or {},
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

        store = await self._current_store()
        results = await store.asimilarity_search_with_score(
            query=query,
            k=top_k,
            expr=self._build_kb_filter(knowledgebase_ids),
            ranker_type="weighted",
            ranker_params={"weights": _DENSE_ONLY_WEIGHTS},
        )
        return [document for document, score in results if score >= min_score]

    async def similar_search_rrf(
        self,
        query: str,
        knowledgebase_ids: list[int],
        top_k: int,
    ) -> list[Document]:
        if top_k <= 0:
            return []

        return await (await self._current_store()).asimilarity_search(
            query=query,
            k=top_k,
            expr=self._build_kb_filter(knowledgebase_ids),
            ranker_type="rrf",
            ranker_params={"k": _RRF_RANK_CONSTANT},
        )

    async def delete_by_kb_id(self, knowledgebase_id: int) -> None:
        deleted = await (await self._current_store()).adelete(
            expr=f"kb_id == {json.dumps(str(knowledgebase_id))}",
        )
        if deleted is False:
            raise RuntimeError(
                f"Milvus failed to delete vectors for knowledgebase {knowledgebase_id}"
            )

    @staticmethod
    def _build_kb_filter(knowledgebase_ids: list[int]) -> str | None:
        kb_ids = [str(kid) for kid in knowledgebase_ids if kid is not None]
        if not kb_ids:
            return None
        return f"kb_id in {json.dumps(kb_ids)}"

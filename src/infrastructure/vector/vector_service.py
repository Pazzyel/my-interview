import logging
from typing import List, Optional

from langchain_core.documents import Document

from common.config import app_config
from common.llm_provider import LlmProviderRegistry
from infrastructure.vector.vector_store import create_vector_store, VectorStore

logger = logging.getLogger(__name__)


class VectorService:
    """
    向量端口服务（Port）。

    对业务层暴露与底层向量库无关的方法：
    - add_documents
    - similar_search
    - delete_by_kb_id

    当前默认持有 Elasticsearch 的 VectorStore，后续替换向量库仅需在 VectorStore 侧调整。
    """

    def __init__(self, store: Optional[VectorStore] = None, registry: LlmProviderRegistry | None = None) -> None:
        self._store: VectorStore | None = store
        self._registry = registry or LlmProviderRegistry()
        self._embedding_identity: int | None = None

    async def _current_store(self) -> VectorStore:
        if self._store is not None and self._embedding_identity is None:
            return self._store
        embedding = await self._registry.get_default_embedding_model()
        if self._store is None or self._embedding_identity != id(embedding):
            self._store = create_vector_store(embedding)
            self._embedding_identity = id(embedding)
        return self._store

    async def add_documents(self, documents: List[Document]) -> None:
        await (await self._current_store()).aadd_documents(documents)

    async def get_retriever(self, search_type: str = "similarity_score_threshold", search_kwargs: Optional[dict] = None):
        return (await self._current_store()).as_retriever(search_type=search_type, search_kwargs=search_kwargs)

    async def similar_search(
        self,
        query: str,
        knowledgebase_ids: List[int],
        top_k: int,
        min_score: float,
    ) -> List[Document]:
        try:
            store = await self._current_store()
            pre_filter = self._build_kb_filter(knowledgebase_ids) if knowledgebase_ids else None
            search_kwargs = {
                "k": max(top_k, 1),
                "score_threshold": min_score,
            }
            if pre_filter is not None:
                search_kwargs["filter"] = pre_filter

            retriever = store.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs=search_kwargs,
            )
            documents = await retriever.ainvoke(query)
            return documents[:top_k]
        except Exception as e:
            logger.warning("向量搜索前置过滤失败，回退到本地过滤: %s", str(e))
            return await self._similar_search_fallback(query, knowledgebase_ids, top_k, min_score)

    async def delete_by_kb_id(self, knowledgebase_id: int) -> None:
        es_client = (await self._current_store()).client
        await es_client.delete_by_query(
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
        knowledgebase_ids: List[int],
        top_k: int,
        min_score: float,
    ) -> List[Document]:
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
            documents = [doc for doc in documents if doc.metadata.get("kb_id") in kb_id_strs]

        return documents[:top_k]

    @staticmethod
    def _build_kb_filter(knowledgebase_ids: List[int]) -> list:
        kb_id_strs = [str(kid) for kid in knowledgebase_ids if kid is not None]
        return [{"terms": {"metadata.kb_id.keyword": kb_id_strs}}]

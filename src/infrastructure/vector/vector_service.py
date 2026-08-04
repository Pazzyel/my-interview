from typing import Any, Protocol, runtime_checkable

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


@runtime_checkable
class VectorService(Protocol):
    """Backend-neutral asynchronous vector database contract."""

    async def add_documents(self, documents: list[Document]) -> None: ...

    async def get_retriever(
        self,
        search_type: str = "similarity_score_threshold",
        search_kwargs: dict[str, Any] | None = None,
    ) -> BaseRetriever: ...

    async def similar_search(
        self,
        query: str,
        knowledgebase_ids: list[int],
        top_k: int,
        min_score: float,
    ) -> list[Document]: ...

    async def similar_search_rrf(
        self,
        query: str,
        knowledgebase_ids: list[int],
        top_k: int,
    ) -> list[Document]: ...

    async def delete_by_kb_id(self, knowledgebase_id: int) -> None: ...

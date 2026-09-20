import hashlib

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from common.config import app_config


class KnowledgeBaseChunkingService:
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50
    SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", " ", ""]

    def __init__(self) -> None:
        self._tokenizer = tiktoken.get_encoding(app_config.tokenizer_name)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.CHUNK_SIZE,
            chunk_overlap=self.CHUNK_OVERLAP,
            length_function=self.token_length,
            separators=self.SEPARATORS,
        )

    def token_length(self, content: str) -> int:
        return len(self._tokenizer.encode(content))

    def split(
        self,
        content: str,
        kb_id: int,
        kb_name: str,
        kb_category: str | None,
    ) -> list[Document]:
        documents = self._splitter.create_documents([content])
        for index, document in enumerate(documents):
            content_hash = hashlib.sha256(document.page_content.encode("utf-8")).hexdigest()[:16]
            document.metadata = {
                "kb_id": str(kb_id),
                "source": kb_name,
                "category": kb_category or "general",
                "chunk_id": f"{kb_id}:{index}:{content_hash}",
                "chunk_index": index,
            }
        return documents

    def manifest(self) -> dict[str, object]:
        return {
            "chunk_size": self.CHUNK_SIZE,
            "chunk_overlap": self.CHUNK_OVERLAP,
            "tokenizer": app_config.tokenizer_name,
            "separators": self.SEPARATORS,
        }

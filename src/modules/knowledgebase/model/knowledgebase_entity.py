from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class VectorStatus(str, Enum):
    """知识库向量化状态"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class KnowledgeBaseEntity(BaseModel):
    """
    知识库纯数据模型

    Pure data model for KnowledgeBase, decoupled from ORM.
    """
    id: Optional[int] = None
    file_hash: str = ""
    name: str = ""
    category: Optional[str] = None
    original_filename: str = ""
    file_size: int = 0
    content_type: Optional[str] = None
    storage_key: Optional[str] = None
    storage_url: Optional[str] = None
    uploaded_at: datetime = datetime.now()
    last_accessed_at: datetime = datetime.now()
    access_count: int = 1
    question_count: int = 0
    vector_status: VectorStatus = VectorStatus.PENDING
    vector_error: Optional[str] = None
    chunk_count: int = 0

    def increment_access_count(self) -> None:
        """更新访问计数和最后访问时间"""
        self.access_count += 1
        self.last_accessed_at = datetime.now()

    def increment_question_count(self) -> None:
        """更新提问计数和最后访问时间"""
        self.question_count += 1
        self.last_accessed_at = datetime.now()

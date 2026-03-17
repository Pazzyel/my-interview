from datetime import datetime
from enum import Enum

from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity


class MessageType(Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"

class RagChatMessageEntity:

    def __init__(self, r_id: int, session_id: int, r_type: str, content: str, message_order: int, created_at: datetime, updated_at: datetime, completed: bool):
        self.id = r_id
        self.session_id = session_id
        self.type = r_type
        self.content = content
        self.message_order = message_order
        self.created_at = created_at
        self.updated_at = updated_at
        self.completed = completed

    id: int
    session_id: int
    type: str  # 'USER' or 'ASSISTANT'
    content: str
    message_order: int
    created_at: datetime
    updated_at: datetime
    completed: bool

class RagChatSessionEntity:

    def __init__(self, r_id: int, title: str, status: str, created_at: datetime, updated_at: datetime, message_count: int, is_pinned: bool, knowledge_bases: list[KnowledgeBaseEntity]):
        self.id = r_id
        self.title = title
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.message_count = message_count
        self.is_pinned = is_pinned
        self.knowledge_bases: list[KnowledgeBaseEntity] = knowledge_bases

    id: int
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    is_pinned: bool

    # 使用 selectin 解决异步懒加载问题 / Use selectin to resolve async lazy loading
    knowledge_bases: list[KnowledgeBaseEntity]
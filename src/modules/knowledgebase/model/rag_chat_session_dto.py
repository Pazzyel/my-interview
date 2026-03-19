from datetime import datetime
from typing import List, Optional

from pydantic import Field

from infrastructure.model.BaseCamelSchema import BaseCamelSchema
from modules.knowledgebase.model.knowledgebase_dto import KnowledgeBaseListItemDTO


class CreateSessionRequest(BaseCamelSchema):
    knowledge_base_ids: List[int] = Field(..., min_length=1)
    title: Optional[str] = None


class UpdateTitleRequest(BaseCamelSchema):
    title: str = Field(..., min_length=1)


class UpdateKnowledgeBasesRequest(BaseCamelSchema):
    knowledge_base_ids: List[int] = Field(..., min_length=1)


class SendMessageRequest(BaseCamelSchema):
    question: str = Field(..., min_length=1)


class SessionDTO(BaseCamelSchema):
    id: int
    title: str
    knowledge_base_ids: List[int]
    created_at: datetime


class SessionListItemDTO(BaseCamelSchema):
    id: int
    title: str
    message_count: int
    knowledge_base_names: List[str]
    updated_at: datetime
    is_pinned: bool


class MessageDTO(BaseCamelSchema):
    id: int
    type: str
    content: str
    created_at: datetime


class SessionDetailDTO(BaseCamelSchema):
    id: int
    title: str
    knowledge_bases: List[KnowledgeBaseListItemDTO]
    messages: List[MessageDTO]
    created_at: datetime
    updated_at: datetime

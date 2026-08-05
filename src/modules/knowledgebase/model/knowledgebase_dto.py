from datetime import datetime
from typing import Optional

from pydantic import Field

from infrastructure.model.BaseCamelSchema import BaseCamelSchema
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.model.knowledgebase_question import QuestionGenStatus


class KnowledgeBaseListItemDTO(BaseCamelSchema):
    """
    知识库列表项数据传输对象

    KnowledgeBase list item Data Transfer Object (DTO).
    """
    id: Optional[int] = Field(default=None, description="知识库ID / Knowledge base ID")
    name: str = Field(..., description="知识库名称 / Knowledge base name")
    category: Optional[str] = Field(default=None, description="知识库分类 / Knowledge base category")
    original_filename: str = Field(..., alias="originalFilename", description="原始文件名 / Original filename")
    file_size: int = Field(..., alias="fileSize", description="文件大小 / File size")
    uploaded_at: datetime = Field(..., alias="uploadedAt", description="上传时间 / Upload time")
    access_count: int = Field(default=0, alias="accessCount", description="访问次数 / Access count")
    question_count: int = Field(default=0, alias="questionCount", description="提问次数 / Question count")
    vector_status: VectorStatus = Field(default=VectorStatus.PENDING, alias="vectorStatus", description="向量化状态 / Vectorization status")
    vector_error: Optional[str] = Field(default=None, alias="vectorError", description="向量化异常信息 / Vectorization error message")
    chunk_count: int = Field(default=0, alias="chunkCount")
    question_gen_status: QuestionGenStatus = Field(default=QuestionGenStatus.NONE, alias="questionGenStatus")
    question_gen_error: Optional[str] = Field(default=None, alias="questionGenError")



class KnowledgeBaseStatsDTO(BaseCamelSchema):
    """
    知识库统计信息数据传输对象

    KnowledgeBase statistics Data Transfer Object (DTO).
    """
    total_count: int = Field(..., alias="totalCount", description="总知识库数量 / Total knowledge base count")
    total_questions: int = Field(..., alias="totalQuestions", description="总提问次数 / Total question count")
    total_access: int = Field(..., alias="totalAccess", description="总访问次数 / Total access count")
    completed_vectors: int = Field(..., alias="completedVectors", description="已完成向量化的知识库数量 / Completed vectorizations count")
    processing_vectors: int = Field(..., alias="processingVectors", description="正在处理向量化的知识库数量 / Processing vectorizations count")


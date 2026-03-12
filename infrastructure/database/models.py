from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Enum as SQLEnum, Table, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from common.models import AsyncTaskStatus
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus

class Base(DeclarativeBase):
    pass

class ResumeORM(Base):
    __tablename__ = 'resumes'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fileHash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    originalFilename: Mapped[str] = mapped_column(String(255), nullable=False)
    fileSize: Mapped[int] = mapped_column(Integer, nullable=False)
    contentType: Mapped[str] = mapped_column(String(100), nullable=False)
    storageKey: Mapped[str] = mapped_column(String(255), nullable=True)
    storageUrl: Mapped[str] = mapped_column(String(255), nullable=True)
    resumeText: Mapped[str] = mapped_column(Text, nullable=True)
    uploadedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    lastAccessedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    accessCount: Mapped[int] = mapped_column(Integer, default=1)
    
    # Store enum as string
    analyzeStatus: Mapped[AsyncTaskStatus] = mapped_column(
        SQLEnum(AsyncTaskStatus, name="async_task_status", create_type=False),
        default=AsyncTaskStatus.PENDING
    )
    analyzeError: Mapped[str] = mapped_column(Text, nullable=True)

class ResumeAnalysisORM(Base):
    __tablename__ = 'resume_analyses'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey('resumes.id'), nullable=False, index=True)
    overallScore: Mapped[int] = mapped_column(Integer, nullable=True)
    contentScore: Mapped[int] = mapped_column(Integer, nullable=True)
    structureScore: Mapped[int] = mapped_column(Integer, nullable=True)
    skillMatchScore: Mapped[int] = mapped_column(Integer, nullable=True)
    expressionScore: Mapped[int] = mapped_column(Integer, nullable=True)
    projectScore: Mapped[int] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    strengthsJson: Mapped[str] = mapped_column(Text, nullable=True)
    suggestionsJson: Mapped[str] = mapped_column(Text, nullable=True)
    analyzedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class KnowledgeBaseORM(Base):
    __tablename__ = 'knowledge_bases'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=True)
    storage_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    access_count: Mapped[int] = mapped_column(Integer, default=1)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_status: Mapped[VectorStatus] = mapped_column(
        SQLEnum(VectorStatus, name="vector_status", create_type=False),
        default=VectorStatus.PENDING
    )
    vector_error: Mapped[str] = mapped_column(String(500), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

# 会话和知识库的多对多关联表
# Many-to-many relationship table between sessions and knowledge bases
rag_session_knowledge_bases = Table(
    'rag_session_knowledge_bases',
    Base.metadata,
    Column('session_id', Integer, ForeignKey('rag_chat_sessions.id'), primary_key=True),
    Column('knowledge_base_id', Integer, ForeignKey('knowledge_bases.id'), primary_key=True)
)

class RagChatSessionORM(Base):
    """
    RAG 聊天会话实体
    RAG Chat Session Entity
    """
    __tablename__ = 'rag_chat_sessions'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 使用 selectin 解决异步懒加载问题 / Use selectin to resolve async lazy loading
    knowledge_bases: Mapped[list["KnowledgeBaseORM"]] = relationship(
        secondary=rag_session_knowledge_bases,
        lazy="selectin"
    )

class RagChatMessageORM(Base):
    """
    RAG 聊天消息实体
    RAG Chat Message Entity
    """
    __tablename__ = 'rag_chat_messages'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('rag_chat_sessions.id'), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False) # 'USER' or 'ASSISTANT'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed: Mapped[bool] = mapped_column(Boolean, default=True)

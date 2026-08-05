from datetime import datetime
from enum import Enum

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, Table, Boolean, Float, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from common.models import AsyncTaskStatus
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.interviewschedule.model import InterviewStatus, InterviewType


class Base(DeclarativeBase):
    pass


class LlmProviderConfigORM(Base):
    __tablename__ = "llm_provider_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_ciphertext: Mapped[str] = mapped_column(String(4096), nullable=False)
    api_key_nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_embedding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


class LlmGlobalSettingORM(Base):
    __tablename__ = "llm_global_setting"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_chat_provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("llm_provider_config.id"), nullable=False
    )
    default_embedding_provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("llm_provider_config.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


class InterviewScheduleORM(Base):
    __tablename__ = "interview_schedule"
    __table_args__ = (
        Index("ix_interview_schedule_time", "interview_time"),
        Index("ix_interview_schedule_status_time", "status", "interview_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(255), nullable=False)
    interview_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    interview_type: Mapped[InterviewType | None] = mapped_column(
        SQLEnum(InterviewType, name="interview_schedule_type", create_type=False), nullable=True
    )
    meeting_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    interviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InterviewStatus] = mapped_column(
        SQLEnum(InterviewStatus, name="interview_schedule_status", create_type=False),
        default=InterviewStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

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


class InterviewSessionStatus(str, Enum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EVALUATED = "EVALUATED"


class InterviewSessionORM(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id"), nullable=True, index=True)
    skill_id: Mapped[str] = mapped_column(String(64), default="java-backend", index=True)
    difficulty: Mapped[str] = mapped_column(String(16), default="mid")
    llm_provider: Mapped[str] = mapped_column(String(50), default="default")
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[InterviewSessionStatus] = mapped_column(
        SQLEnum(InterviewSessionStatus, name="interview_session_status", create_type=False),
        default=InterviewSessionStatus.CREATED,
    )
    questions_json: Mapped[str] = mapped_column(Text, nullable=True)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=True)
    overall_feedback: Mapped[str] = mapped_column(Text, nullable=True)
    strengths_json: Mapped[str] = mapped_column(Text, nullable=True)
    improvements_json: Mapped[str] = mapped_column(Text, nullable=True)
    reference_answers_json: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    evaluate_status: Mapped[AsyncTaskStatus] = mapped_column(
        SQLEnum(AsyncTaskStatus, name="async_task_status", create_type=False),
        default=AsyncTaskStatus.PENDING,
    )
    evaluate_error: Mapped[str] = mapped_column(String(500), nullable=True)

    answers: Mapped[list["InterviewAnswerORM"]] = relationship(
        "InterviewAnswerORM",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InterviewAnswerORM(Base):
    __tablename__ = "interview_answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_pk_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False, index=True)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    user_answer: Mapped[str] = mapped_column(Text, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, nullable=True)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=True)
    key_points_json: Mapped[str] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    session: Mapped[InterviewSessionORM] = relationship("InterviewSessionORM", back_populates="answers")


class VoiceInterviewSessionStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VoiceInterviewPhase(str, Enum):
    INTRO = "INTRO"
    TECH = "TECH"
    PROJECT = "PROJECT"
    HR = "HR"
    COMPLETED = "COMPLETED"


class VoiceInterviewMessageType(str, Enum):
    USER_SPEECH = "USER_SPEECH"
    AI_SPEECH = "AI_SPEECH"
    SYSTEM = "SYSTEM"
    SUMMARY = "SUMMARY"


class VoiceInterviewSessionORM(Base):
    __tablename__ = "voice_interview_sessions"
    __table_args__ = (
        Index("ix_voice_sessions_user_created", "user_id", "created_at"),
        Index("ix_voice_sessions_status_updated", "status", "updated_at"),
        Index("ix_voice_sessions_evaluate_updated", "evaluate_status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # TODO(multi-user): reserved compatibility field; no authentication or ownership checks yet.
    user_id: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    role_type: Mapped[str] = mapped_column(String(128), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), default="java-backend", nullable=False, index=True)
    difficulty: Mapped[str] = mapped_column(String(16), default="mid", nullable=False)
    custom_jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    intro_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tech_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    project_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hr_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(50), default="default", nullable=False)
    current_phase: Mapped[VoiceInterviewPhase] = mapped_column(
        SQLEnum(VoiceInterviewPhase, name="voice_interview_phase", create_type=False), nullable=False
    )
    status: Mapped[VoiceInterviewSessionStatus] = mapped_column(
        SQLEnum(VoiceInterviewSessionStatus, name="voice_interview_session_status", create_type=False),
        default=VoiceInterviewSessionStatus.IN_PROGRESS, nullable=False,
    )
    planned_duration: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    actual_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_paused_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evaluate_status: Mapped[AsyncTaskStatus | None] = mapped_column(
        SQLEnum(AsyncTaskStatus, name="async_task_status", create_type=False), nullable=True
    )
    evaluate_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    messages: Mapped[list["VoiceInterviewMessageORM"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    evaluation: Mapped["VoiceInterviewEvaluationORM | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )


class VoiceInterviewMessageORM(Base):
    __tablename__ = "voice_interview_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_num", name="uq_voice_messages_session_sequence"),
        Index("ix_voice_messages_session_type_sequence", "session_id", "message_type", "sequence_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("voice_interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_type: Mapped[VoiceInterviewMessageType] = mapped_column(
        SQLEnum(VoiceInterviewMessageType, name="voice_interview_message_type", create_type=False), nullable=False
    )
    phase: Mapped[VoiceInterviewPhase | None] = mapped_column(
        SQLEnum(VoiceInterviewPhase, name="voice_interview_phase", create_type=False), nullable=True
    )
    user_recognized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_covered_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    session: Mapped[VoiceInterviewSessionORM] = relationship(back_populates="messages")


class VoiceInterviewEvaluationORM(Base):
    __tablename__ = "voice_interview_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("voice_interview_sessions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_evaluations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    improvements_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    interviewer_role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interview_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    session: Mapped[VoiceInterviewSessionORM] = relationship(back_populates="evaluation")

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
    # 这个字段是中间表加载出来的，rag_chat_session表没有这个字段
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
    message_order: Mapped[int] = mapped_column(Integer, nullable=False) # 这个消息在会话里的序号
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed: Mapped[bool] = mapped_column(Boolean, default=True)

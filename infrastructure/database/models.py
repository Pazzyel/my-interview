from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from common.models import AsyncTaskStatus

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

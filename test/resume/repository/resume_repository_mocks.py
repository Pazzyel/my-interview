from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from common.models import AsyncTaskStatus
from infrastructure.database.models import Base
from modules.resume.model.resume_entity import ResumeAnalysisEntity, ResumeEntity


class InMemorySqliteSessionFactory:
    """
    该 Mock 替代了生产环境中的真实数据库连接（如 PostgreSQL）。
    它提供 sqlite 内存数据库，用于在测试中隔离 Repository 的 SQL 行为。
    """

    def __init__(self) -> None:
        self._engine = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    async def init(self) -> None:
        """
        该初始化逻辑替代了应用启动时的真实数据库建连与建表流程。
        """
        self._engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self._session_maker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self):
        """
        该上下文管理器替代了生产代码中的会话工厂（session factory）注入。
        """
        if self._session_maker is None:
            raise RuntimeError("InMemorySqliteSessionFactory 尚未初始化，请先调用 init()")

        async with self._session_maker() as db:
            yield db

    async def dispose(self) -> None:
        """
        该销毁逻辑替代了应用关闭时对真实数据库连接池的回收。
        """
        if self._engine is not None:
            await self._engine.dispose()


def build_resume_entity(
    *,
    file_hash: str,
    filename: str,
    uploaded_at: datetime,
    status: AsyncTaskStatus = AsyncTaskStatus.PENDING,
) -> ResumeEntity:
    """构造测试用 ResumeEntity（替代业务层真实入参构造）。"""
    return ResumeEntity(
        fileHash=file_hash,
        originalFilename=filename,
        fileSize=2048,
        contentType="application/pdf",
        storageKey=f"resume/{filename}",
        storageUrl=f"https://example.test/{filename}",
        resumeText="这是测试简历文本",
        uploadedAt=uploaded_at,
        lastAccessedAt=uploaded_at,
        accessCount=1,
        analyzeStatus=status,
        analyzeError=None,
    )


def build_analysis_entity(
    *,
    resume_id: int,
    overall_score: int,
    analyzed_at: datetime,
) -> ResumeAnalysisEntity:
    """构造测试用 ResumeAnalysisEntity（替代分析服务真实输出）。"""
    return ResumeAnalysisEntity(
        resume_id=resume_id,
        overallScore=overall_score,
        contentScore=overall_score - 1,
        structureScore=overall_score - 2,
        skillMatchScore=overall_score - 3,
        expressionScore=overall_score - 4,
        projectScore=overall_score - 5,
        summary="测试分析摘要",
        strengthsJson='["亮点一", "亮点二"]',
        suggestionsJson='[{"title": "建议", "detail": "补充项目量化指标"}]',
        analyzedAt=analyzed_at,
    )

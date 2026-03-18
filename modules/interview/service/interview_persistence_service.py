from common.exceptions import BusinessException, ErrorCode
from modules.interview.model.interview_entity import InterviewSessionEntity
from modules.interview.repository.interview_repository import InterviewRepository
from sqlalchemy.ext.asyncio import AsyncSession


class InterviewPersistenceService:
    """
    面试持久化服务，负责历史会话查询和删除。
    Interview persistence service for non-AI interview CRUD operations.
    """

    def __init__(self, interview_repository: InterviewRepository) -> None:
        self.interview_repository = interview_repository

    async def find_by_resume_id(self, db: AsyncSession, resume_id: int) -> list[InterviewSessionEntity]:
        return await self.interview_repository.find_by_resume_id(db, resume_id)

    async def delete_sessions_by_resume_id(self, db: AsyncSession, resume_id: int) -> None:
        await self.interview_repository.delete_by_resume_id(db, resume_id)

    async def delete_session_by_session_id(self, db: AsyncSession, session_id: str) -> None:
        await self.interview_repository.delete_by_session_id(db, session_id)

    async def find_unfinished_session_or_throw(self, db: AsyncSession, resume_id: int) -> InterviewSessionEntity:
        session: InterviewSessionEntity | None = await self.interview_repository.find_unfinished_by_resume_id(db, resume_id)
        if session is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "未找到未完成的面试会话")
        return session

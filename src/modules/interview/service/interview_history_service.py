from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.interview.model.interview_dto import InterviewDetailDTO
from modules.interview.repository.interview_repository import InterviewRepository


class InterviewHistoryService:
    """
    面试历史服务，负责会话详情查询。
    Interview history service for session detail query.
    """

    def __init__(self, interview_repository: InterviewRepository) -> None:
        self.interview_repository = interview_repository

    async def get_interview_detail(self, db: AsyncSession, session_id: str) -> InterviewDetailDTO:
        """
        生成指定会话的面试详情内容。
        Build interview detail content for the specified session.
        """
        detail: InterviewDetailDTO | None = await self.interview_repository.find_detail_by_session_id(db, session_id)
        if detail is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")
        return detail

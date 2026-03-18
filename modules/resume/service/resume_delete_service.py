from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from infrastructure.file.file_storage_service import FileStorageService
from modules.interview.service.interview_persistence_service import InterviewPersistenceService
from modules.resume.repository.resume_repository import ResumeRepository


class ResumeDeleteService:
    """
    简历删除服务，负责简历及关联数据删除。
    Resume delete service for resume and related interview cleanup.
    """

    def __init__(
        self,
        resume_repository: ResumeRepository,
        interview_persistence_service: InterviewPersistenceService,
        file_storage_service: FileStorageService,
    ) -> None:
        self.resume_repository = resume_repository
        self.interview_persistence_service = interview_persistence_service
        self.file_storage_service = file_storage_service

    async def delete_resume(self, db: AsyncSession, resume_id: int) -> None:
        resume = await self.resume_repository.find_by_id(db, resume_id)
        if resume is None:
            raise BusinessException(ErrorCode.RESUME_NOT_FOUND, "简历不存在")

        if resume.storageKey is not None and resume.storageKey.strip() != "":
            try:
                await self.file_storage_service.delete_file(resume.storageKey)
            except Exception:
                pass

        await self.interview_persistence_service.delete_sessions_by_resume_id(db, resume_id)
        await self.resume_repository.delete_by_id(db, resume_id)

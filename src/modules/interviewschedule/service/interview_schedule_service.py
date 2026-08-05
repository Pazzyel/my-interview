from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import InterviewScheduleORM
from modules.interviewschedule.model import (
    CreateInterviewRequest,
    InterviewScheduleDTO,
    InterviewStatus,
)
from modules.interviewschedule.repository import InterviewScheduleRepository


class InterviewScheduleService:
    def __init__(self, repository: InterviewScheduleRepository) -> None:
        self.repository = repository

    async def create(
        self,
        db: AsyncSession,
        request: CreateInterviewRequest,
    ) -> InterviewScheduleDTO:
        return self._to_dto(await self.repository.create(db, request))

    async def get_by_id(self, db: AsyncSession, schedule_id: int) -> InterviewScheduleDTO:
        return self._to_dto(await self._get_or_raise(db, schedule_id))

    async def get_all(
        self,
        db: AsyncSession,
        status: InterviewStatus | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[InterviewScheduleDTO]:
        rows = await self.repository.list(db, status=status, start=start, end=end)
        return [self._to_dto(row) for row in rows]

    async def update(
        self,
        db: AsyncSession,
        schedule_id: int,
        request: CreateInterviewRequest,
    ) -> InterviewScheduleDTO:
        row = await self._get_or_raise(db, schedule_id)
        return self._to_dto(await self.repository.update(db, row, request))

    async def delete(self, db: AsyncSession, schedule_id: int) -> None:
        await self.repository.delete(db, await self._get_or_raise(db, schedule_id))

    async def update_status(
        self,
        db: AsyncSession,
        schedule_id: int,
        status: InterviewStatus,
    ) -> InterviewScheduleDTO:
        row = await self._get_or_raise(db, schedule_id)
        return self._to_dto(await self.repository.update_status(db, row, status))

    async def _get_or_raise(
        self,
        db: AsyncSession,
        schedule_id: int,
    ) -> InterviewScheduleORM:
        row = await self.repository.get(db, schedule_id)
        if row is None:
            raise BusinessException(
                ErrorCode.INTERVIEW_SCHEDULE_NOT_FOUND,
                f"面试日程不存在: {schedule_id}",
            )
        return row

    @staticmethod
    def _to_dto(row: InterviewScheduleORM) -> InterviewScheduleDTO:
        return InterviewScheduleDTO.model_validate(row)

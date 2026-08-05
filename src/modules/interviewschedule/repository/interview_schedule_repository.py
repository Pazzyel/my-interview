from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import InterviewScheduleORM
from modules.interviewschedule.model import CreateInterviewRequest, InterviewStatus


class InterviewScheduleRepository:
    async def create(
        self,
        db: AsyncSession,
        request: CreateInterviewRequest,
    ) -> InterviewScheduleORM:
        row = InterviewScheduleORM(
            **request.model_dump(by_alias=False),
            status=InterviewStatus.PENDING,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    async def get(self, db: AsyncSession, schedule_id: int) -> InterviewScheduleORM | None:
        return await db.get(InterviewScheduleORM, schedule_id)

    async def list(
        self,
        db: AsyncSession,
        status: InterviewStatus | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[InterviewScheduleORM]:
        statement = select(InterviewScheduleORM)
        if start is not None and end is not None:
            statement = statement.where(InterviewScheduleORM.interview_time.between(start, end))
        elif status is not None:
            statement = statement.where(InterviewScheduleORM.status == status)
        statement = statement.order_by(InterviewScheduleORM.interview_time, InterviewScheduleORM.id)
        return list((await db.scalars(statement)).all())

    async def update(
        self,
        db: AsyncSession,
        row: InterviewScheduleORM,
        request: CreateInterviewRequest,
    ) -> InterviewScheduleORM:
        for field, value in request.model_dump(by_alias=False).items():
            setattr(row, field, value)
        await db.flush()
        await db.refresh(row)
        return row

    async def update_status(
        self,
        db: AsyncSession,
        row: InterviewScheduleORM,
        status: InterviewStatus,
    ) -> InterviewScheduleORM:
        row.status = status
        await db.flush()
        await db.refresh(row)
        return row

    async def delete(self, db: AsyncSession, row: InterviewScheduleORM) -> None:
        await db.delete(row)
        await db.flush()

    async def cancel_expired_pending(self, db: AsyncSession, cutoff: datetime) -> int:
        result = await db.execute(
            update(InterviewScheduleORM)
            .where(
                InterviewScheduleORM.status == InterviewStatus.PENDING,
                InterviewScheduleORM.interview_time < cutoff,
            )
            .values(status=InterviewStatus.CANCELLED, updated_at=cutoff)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

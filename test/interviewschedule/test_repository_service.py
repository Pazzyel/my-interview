import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import Base
from modules.interviewschedule.model import CreateInterviewRequest, InterviewStatus, InterviewType
from modules.interviewschedule.repository import InterviewScheduleRepository
from modules.interviewschedule.service import InterviewScheduleService


@asynccontextmanager
async def database(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def request(company: str, interview_time: datetime) -> CreateInterviewRequest:
    return CreateInterviewRequest(
        companyName=company,
        position="Python 开发工程师",
        interviewTime=interview_time,
        interviewType="VIDEO",
        meetingLink="https://meeting.example.test/room",
    )


def test_crud_filters_and_missing_schedule(tmp_path):
    async def scenario():
        async with database(tmp_path / "schedule.db") as db:
            repository = InterviewScheduleRepository()
            service = InterviewScheduleService(repository)
            now = datetime(2026, 8, 5, 12, 0)

            first = await service.create(db, request("甲公司", now + timedelta(days=1)))
            second = await service.create(db, request("乙公司", now + timedelta(days=2)))
            assert first.status == InterviewStatus.PENDING
            assert first.round_number == 1

            updated_request = request("甲公司（更新）", now + timedelta(days=3))
            updated_request.interview_type = InterviewType.ONSITE
            updated = await service.update(db, first.id, updated_request)
            assert updated.company_name == "甲公司（更新）"
            assert updated.status == InterviewStatus.PENDING

            completed = await service.update_status(db, second.id, InterviewStatus.COMPLETED)
            assert completed.status == InterviewStatus.COMPLETED
            assert [item.id for item in await service.get_all(db, InterviewStatus.COMPLETED)] == [second.id]

            ranged = await service.get_all(
                db,
                InterviewStatus.COMPLETED,
                now + timedelta(days=2, hours=12),
                now + timedelta(days=3, hours=12),
            )
            assert [item.id for item in ranged] == [first.id]

            await service.delete(db, first.id)
            assert await repository.get(db, first.id) is None
            with pytest.raises(BusinessException) as exc_info:
                await service.get_by_id(db, first.id)
            assert exc_info.value.code == ErrorCode.INTERVIEW_SCHEDULE_NOT_FOUND

    asyncio.run(scenario())


def test_cancel_expired_only_updates_pending_rows(tmp_path):
    async def scenario():
        async with database(tmp_path / "expired.db") as db:
            repository = InterviewScheduleRepository()
            service = InterviewScheduleService(repository)
            cutoff = datetime(2026, 8, 5, 12, 0)
            expired = await service.create(db, request("过期公司", cutoff - timedelta(minutes=1)))
            completed = await service.create(db, request("已完成公司", cutoff - timedelta(hours=1)))
            future = await service.create(db, request("未来公司", cutoff + timedelta(hours=1)))
            await service.update_status(db, completed.id, InterviewStatus.COMPLETED)

            assert await repository.cancel_expired_pending(db, cutoff) == 1
            assert (await service.get_by_id(db, expired.id)).status == InterviewStatus.CANCELLED
            assert (await service.get_by_id(db, completed.id)).status == InterviewStatus.COMPLETED
            assert (await service.get_by_id(db, future.id)).status == InterviewStatus.PENDING

    asyncio.run(scenario())

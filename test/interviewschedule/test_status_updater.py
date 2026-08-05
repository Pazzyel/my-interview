import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from infrastructure.database.models import Base
from modules.interviewschedule.model import CreateInterviewRequest, InterviewStatus
from modules.interviewschedule.repository import InterviewScheduleRepository
from modules.interviewschedule.service import InterviewScheduleService, ScheduleStatusUpdater


def test_status_updater_run_once_and_lifecycle(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'updater.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        repository = InterviewScheduleRepository()
        service = InterviewScheduleService(repository)
        cutoff = datetime.now()
        async with maker() as db:
            schedule = await service.create(
                db,
                CreateInterviewRequest(
                    companyName="过期公司",
                    position="Python 工程师",
                    interviewTime=cutoff - timedelta(minutes=1),
                ),
            )
            await db.commit()

        updater = ScheduleStatusUpdater(maker, repository, interval_seconds=0.01)
        assert await updater.run_once(cutoff) == 1
        await updater.start()
        await asyncio.sleep(0.03)
        await updater.shutdown()
        assert updater._task is None

        async with maker() as db:
            assert (await service.get_by_id(db, schedule.id)).status == InterviewStatus.CANCELLED
        await engine.dispose()

    asyncio.run(scenario())

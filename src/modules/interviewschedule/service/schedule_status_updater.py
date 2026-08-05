import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.interviewschedule.repository import InterviewScheduleRepository

logger = logging.getLogger(__name__)


class ScheduleStatusUpdater:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repository: InterviewScheduleRepository,
        interval_seconds: float = 3600,
    ) -> None:
        self.session_factory = session_factory
        self.repository = repository
        self.interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="interview-schedule-status-updater")

    async def shutdown(self) -> None:
        task = self._task
        if task is None:
            return
        self._stop_event.set()
        await task
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("更新过期面试日程状态失败")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    async def run_once(self, cutoff: datetime | None = None) -> int:
        async with self.session_factory() as db:
            try:
                updated = await self.repository.cancel_expired_pending(db, cutoff or datetime.now())
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        if updated:
            logger.info("已将 %s 条过期面试日程更新为 CANCELLED", updated)
        return updated

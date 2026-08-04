import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode


class InterviewCreationCoordinator:
    """Serializes creation requests sharing the same idempotency key.

    MySQL named locks cover multiple application instances. The in-process lock
    is retained for SQLite/tests and local development.
    """

    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._locks: dict[str, asyncio.Lock] = {}
        self._users: dict[str, int] = {}

    @asynccontextmanager
    async def lock(self, db: AsyncSession, request_id: str) -> AsyncIterator[None]:
        dialect_name = self._dialect_name(db)
        if dialect_name == "mysql":
            lock_name = f"interview:create:{hashlib.sha256(request_id.encode()).hexdigest()[:40]}"
            acquired = (await db.execute(
                text("SELECT GET_LOCK(:lock_name, 185)"), {"lock_name": lock_name}
            )).scalar_one_or_none()
            if acquired != 1:
                raise BusinessException(ErrorCode.BAD_REQUEST, "创建面试请求处理中，请稍后重试")
            try:
                yield
            finally:
                await db.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
            return

        async with self._guard:
            item_lock = self._locks.setdefault(request_id, asyncio.Lock())
            self._users[request_id] = self._users.get(request_id, 0) + 1
        try:
            async with item_lock:
                yield
        finally:
            async with self._guard:
                remaining_users = self._users[request_id] - 1
                if remaining_users == 0:
                    self._locks.pop(request_id, None)
                    self._users.pop(request_id, None)
                else:
                    self._users[request_id] = remaining_users

    @staticmethod
    def _dialect_name(db: AsyncSession) -> str | None:
        bind = getattr(db, "bind", None)
        dialect = getattr(bind, "dialect", None)
        name = getattr(dialect, "name", None)
        return name if isinstance(name, str) else None

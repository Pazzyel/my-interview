"""
RagChatRepository 的 SQLite 内存数据库测试。

覆盖 count_messages_by_type 方法。
"""
import asyncio
from datetime import datetime
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from infrastructure.database.models import RagChatSessionORM, RagChatMessageORM
from modules.knowledgebase.repository.rag_chat_repository import RagChatRepository
from knowledgebase_repository_mocks import InMemorySqliteSessionFactory


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def sqlite_factory() -> InMemorySqliteSessionFactory:
    factory = InMemorySqliteSessionFactory()
    _run(factory.init())
    try:
        yield factory
    finally:
        _run(factory.dispose())


# 测试功能：count_messages_by_type 统计指定类型的消息数量。
def test_count_messages_by_type(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = RagChatRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            # 先创建一个 session
            session_orm = RagChatSessionORM(
                title="测试会话",
                status="ACTIVE",
                created_at=datetime(2026, 3, 10, 10, 0, 0),
                updated_at=datetime(2026, 3, 10, 10, 0, 0),
                message_count=0,
                is_pinned=False,
            )
            db.add(session_orm)
            await db.flush()

            # 添加消息
            msg1 = RagChatMessageORM(
                session_id=session_orm.id,
                type="USER",
                content="你好",
                message_order=1,
                created_at=datetime(2026, 3, 10, 10, 1, 0),
                updated_at=datetime(2026, 3, 10, 10, 1, 0),
                completed=True,
            )
            msg2 = RagChatMessageORM(
                session_id=session_orm.id,
                type="ASSISTANT",
                content="你好！有什么可以帮助你的？",
                message_order=2,
                created_at=datetime(2026, 3, 10, 10, 1, 30),
                updated_at=datetime(2026, 3, 10, 10, 1, 30),
                completed=True,
            )
            msg3 = RagChatMessageORM(
                session_id=session_orm.id,
                type="USER",
                content="什么是JVM？",
                message_order=3,
                created_at=datetime(2026, 3, 10, 10, 2, 0),
                updated_at=datetime(2026, 3, 10, 10, 2, 0),
                completed=True,
            )
            db.add_all([msg1, msg2, msg3])
            await db.commit()

            user_count = await repo.count_messages_by_type(db, "USER")
            assistant_count = await repo.count_messages_by_type(db, "ASSISTANT")

            assert user_count == 2
            assert assistant_count == 1

    _run(_scenario())


# 测试功能：count_messages_by_type 无数据时返回 0。
def test_count_messages_by_type_empty(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = RagChatRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            count = await repo.count_messages_by_type(db, "USER")
            assert count == 0

    _run(_scenario())

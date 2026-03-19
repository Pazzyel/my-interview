import asyncio
from datetime import datetime, timedelta
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

from common.models import AsyncTaskStatus
from modules.resume.repository.resume_repository import ResumeRepository
from resume_repository_mocks import (
    InMemorySqliteSessionFactory,
    build_analysis_entity,
    build_resume_entity,
)


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


# 测试功能：save + exists_by_id + find_by_id 的基础读写流程。
def test_save_and_find_resume(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repository = ResumeRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            uploaded_at = datetime(2026, 1, 10, 10, 0, 0)
            resume = build_resume_entity(
                file_hash="hash-save-find",
                filename="save_find.pdf",
                uploaded_at=uploaded_at,
            )

            saved = await repository.save(db, resume)
            await db.commit()

            assert saved.id is not None
            assert await repository.exists_by_id(db, saved.id) is True

            found = await repository.find_by_id(db, saved.id)
            assert found is not None
            assert found.fileHash == "hash-save-find"
            assert found.originalFilename == "save_find.pdf"

    _run(_scenario())


# 测试功能：find_by_hash 可以按文件哈希定位简历，且不存在时返回 None。
def test_find_by_hash_and_missing_case(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repository = ResumeRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            resume = build_resume_entity(
                file_hash="hash-lookup",
                filename="lookup.pdf",
                uploaded_at=datetime(2026, 1, 10, 11, 0, 0),
            )
            await repository.save(db, resume)
            await db.commit()

            found = await repository.find_by_hash(db, "hash-lookup")
            missing = await repository.find_by_hash(db, "not-exist")

            assert found is not None
            assert found.originalFilename == "lookup.pdf"
            assert missing is None

    _run(_scenario())


# 测试功能：find_all_ordered 按 uploadedAt 倒序返回。
def test_find_all_ordered_by_uploaded_time_desc(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repository = ResumeRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 1, 10, 9, 0, 0)
            first = build_resume_entity(
                file_hash="hash-old",
                filename="old.pdf",
                uploaded_at=base_time,
            )
            second = build_resume_entity(
                file_hash="hash-new",
                filename="new.pdf",
                uploaded_at=base_time + timedelta(hours=1),
            )

            await repository.save(db, first)
            await repository.save(db, second)
            await db.commit()

            results = await repository.find_all_ordered(db)
            assert [item.fileHash for item in results] == ["hash-new", "hash-old"]

    _run(_scenario())


# 测试功能：update_analyze_status 可以更新状态和错误信息，并在目标不存在时返回 False。
def test_update_analyze_status(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repository = ResumeRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            resume = build_resume_entity(
                file_hash="hash-status",
                filename="status.pdf",
                uploaded_at=datetime(2026, 1, 10, 12, 0, 0),
            )
            saved = await repository.save(db, resume)
            await db.commit()

            updated = await repository.update_analyze_status(
                db,
                resume_id=saved.id,
                status=AsyncTaskStatus.FAILED,
                analyze_error="LLM超时",
            )
            await db.commit()

            found = await repository.find_by_id(db, saved.id)
            assert updated is True
            assert found is not None
            assert found.analyzeStatus == AsyncTaskStatus.FAILED
            assert found.analyzeError == "LLM超时"

            missing = await repository.update_analyze_status(
                db,
                resume_id=99999,
                status=AsyncTaskStatus.COMPLETED,
                analyze_error=None,
            )
            assert missing is False

    _run(_scenario())


# 测试功能：save_analysis + find_analyses_by_resume_id 按 analyzedAt 倒序返回分析记录。
def test_save_analysis_and_find_analyses_ordered(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repository = ResumeRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            resume = build_resume_entity(
                file_hash="hash-analysis-list",
                filename="analysis_list.pdf",
                uploaded_at=datetime(2026, 1, 10, 13, 0, 0),
            )
            saved_resume = await repository.save(db, resume)
            await db.commit()

            old_analysis = build_analysis_entity(
                resume_id=saved_resume.id,
                overall_score=75,
                analyzed_at=datetime(2026, 1, 10, 13, 30, 0),
            )
            new_analysis = build_analysis_entity(
                resume_id=saved_resume.id,
                overall_score=90,
                analyzed_at=datetime(2026, 1, 10, 13, 40, 0),
            )

            saved_old = await repository.save_analysis(db, old_analysis)
            saved_new = await repository.save_analysis(db, new_analysis)
            await db.commit()

            assert saved_old.id is not None
            assert saved_new.id is not None

            analyses = await repository.find_analyses_by_resume_id(db, saved_resume.id)
            assert [item.overallScore for item in analyses] == [90, 75]

    _run(_scenario())


# 测试功能：get_latest_analysis_as_dto 能返回最新记录并解析 strengths/suggestions JSON。
def test_get_latest_analysis_as_dto(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repository = ResumeRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            resume = build_resume_entity(
                file_hash="hash-latest-dto",
                filename="latest_dto.pdf",
                uploaded_at=datetime(2026, 1, 10, 14, 0, 0),
            )
            saved_resume = await repository.save(db, resume)
            await db.commit()

            old_analysis = build_analysis_entity(
                resume_id=saved_resume.id,
                overall_score=80,
                analyzed_at=datetime(2026, 1, 10, 14, 10, 0),
            )
            latest_analysis = build_analysis_entity(
                resume_id=saved_resume.id,
                overall_score=95,
                analyzed_at=datetime(2026, 1, 10, 14, 20, 0),
            )

            await repository.save_analysis(db, old_analysis)
            await repository.save_analysis(db, latest_analysis)
            await db.commit()

            dto = await repository.get_latest_analysis_as_dto(db, saved_resume.id)
            missing = await repository.get_latest_analysis_as_dto(db, 99999)

            assert dto is not None
            assert dto.overallScore == 95
            assert dto.strengths == ["亮点一", "亮点二"]
            assert dto.suggestions == [{"title": "建议", "detail": "补充项目量化指标"}]
            assert missing is None

    _run(_scenario())


# 测试功能：delete_by_id 会删除简历及其关联分析记录。
def test_delete_by_id_removes_resume_and_analyses(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repository = ResumeRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            resume = build_resume_entity(
                file_hash="hash-delete",
                filename="delete.pdf",
                uploaded_at=datetime(2026, 1, 10, 15, 0, 0),
            )
            saved_resume = await repository.save(db, resume)
            await db.commit()

            analysis = build_analysis_entity(
                resume_id=saved_resume.id,
                overall_score=88,
                analyzed_at=datetime(2026, 1, 10, 15, 10, 0),
            )
            await repository.save_analysis(db, analysis)
            await db.commit()

            await repository.delete_by_id(db, saved_resume.id)
            await db.commit()

            deleted_resume = await repository.find_by_id(db, saved_resume.id)
            analyses = await repository.find_analyses_by_resume_id(db, saved_resume.id)

            assert deleted_resume is None
            assert analyses == []

    _run(_scenario())

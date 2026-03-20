"""
测试 InterviewPersistenceService 的核心逻辑。
主要验证参数透传以及边界条件下抛出的 BusinessException。
"""
import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import asyncio
from common.exceptions import BusinessException
from modules.interview.service.interview_persistence_service import InterviewPersistenceService
from interview_service_mocks import MockInterviewRepository, build_mock_session_entity


@pytest.fixture
def mock_repo() -> MockInterviewRepository:
    return MockInterviewRepository()


@pytest.fixture
def persistence_service(mock_repo: MockInterviewRepository) -> InterviewPersistenceService:
    return InterviewPersistenceService(interview_repository=mock_repo) # type: ignore


def test_find_by_resume_id(persistence_service: InterviewPersistenceService, mock_repo: MockInterviewRepository) -> None:
    db = AsyncMock()
    mock_entity = build_mock_session_entity(session_id="session1")
    mock_repo.find_by_resume_id.return_value = [mock_entity]

    result = asyncio.run(persistence_service.find_by_resume_id(db, 10))
    
    assert len(result) == 1
    assert result[0].sessionId == "session1"
    mock_repo.find_by_resume_id.assert_awaited_once_with(db, 10)


def test_delete_sessions(persistence_service: InterviewPersistenceService, mock_repo: MockInterviewRepository) -> None:
    db = AsyncMock()

    asyncio.run(persistence_service.delete_sessions_by_resume_id(db, 10))
    mock_repo.delete_by_resume_id.assert_awaited_once_with(db, 10)

    asyncio.run(persistence_service.delete_session_by_session_id(db, "session2"))
    mock_repo.delete_by_session_id.assert_awaited_once_with(db, "session2")


def test_find_unfinished_session_or_throw_success(persistence_service: InterviewPersistenceService, mock_repo: MockInterviewRepository) -> None:
    db = AsyncMock()
    mock_entity = build_mock_session_entity(session_id="unfinished_session")
    mock_repo.find_unfinished_by_resume_id.return_value = mock_entity

    result = asyncio.run(persistence_service.find_unfinished_session_or_throw(db, 10))
    
    assert result.sessionId == "unfinished_session"
    mock_repo.find_unfinished_by_resume_id.assert_awaited_once_with(db, 10)


def test_find_unfinished_session_or_throw_raises(persistence_service: InterviewPersistenceService, mock_repo: MockInterviewRepository) -> None:
    db = AsyncMock()
    mock_repo.find_unfinished_by_resume_id.return_value = None

    with pytest.raises(BusinessException, match="未找到未完成的面试会话"):
        asyncio.run(persistence_service.find_unfinished_session_or_throw(db, 10))

    mock_repo.find_unfinished_by_resume_id.assert_awaited_once_with(db, 10)

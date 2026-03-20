"""
测试 InterviewHistoryService 的核心逻辑。
主要验证获取会话详情时的 DTO 返回和异常处理。
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
from datetime import datetime
from common.exceptions import BusinessException
from modules.interview.service.interview_history_service import InterviewHistoryService
from modules.interview.model.interview_dto import InterviewDetailDTO
from interview_service_mocks import MockInterviewRepository


@pytest.fixture
def mock_repo() -> MockInterviewRepository:
    return MockInterviewRepository()


@pytest.fixture
def history_service(mock_repo: MockInterviewRepository) -> InterviewHistoryService:
    return InterviewHistoryService(interview_repository=mock_repo) # type: ignore


def test_get_interview_detail_success(history_service: InterviewHistoryService, mock_repo: MockInterviewRepository) -> None:
    # 构造假数据
    db = AsyncMock()
    fake_detail_dto = InterviewDetailDTO(
        id=1,
        sessionId="history-session",
        totalQuestions=5,
        status="COMPLETED",
        evaluateStatus="PENDING",
        evaluateError=None,
        overallScore=0,
        overallFeedback="",
        createdAt=datetime.now(),
        completedAt=None,
        questions=[],
        strengths=[],
        improvements=[],
        referenceAnswers=[],
        answers=[]
    )
    mock_repo.find_detail_by_session_id.return_value = fake_detail_dto

    result = asyncio.run(history_service.get_interview_detail(db, "history-session"))
    
    assert result.sessionId == "history-session"
    assert result.totalQuestions == 5
    mock_repo.find_detail_by_session_id.assert_awaited_once_with(db, "history-session")


def test_get_interview_detail_not_found(history_service: InterviewHistoryService, mock_repo: MockInterviewRepository) -> None:
    db = AsyncMock()
    # 模拟仓储返回空
    mock_repo.find_detail_by_session_id.return_value = None

    with pytest.raises(BusinessException, match="面试会话不存在"):
        asyncio.run(history_service.get_interview_detail(db, "not_exist_session"))

    mock_repo.find_detail_by_session_id.assert_awaited_once_with(db, "not_exist_session")

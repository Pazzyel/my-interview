"""
interview_service_mocks.py

为 Interview 服务层的多分支核心逻辑测试提供集中的 Mock 对象。
"""
from typing import Optional, Any
from unittest.mock import AsyncMock, MagicMock
from infrastructure.database.models import InterviewSessionORM, ResumeORM


class MockInterviewRepository:
    def __init__(self):
        self.create_session = AsyncMock()
        self.update_session_status = AsyncMock()
        self.update_evaluate_status = AsyncMock()
        self.update_session_questions_json = AsyncMock()
        self.update_session_progress = AsyncMock()
        self.save_report = AsyncMock()
        self.upsert_answer = AsyncMock()
        self.get_resume_text_by_session_id = AsyncMock(return_value="Mocked Resume Text")
        self.list_historical_questions_by_resume_id = AsyncMock(return_value=["Mock Q1", "Mock Q2"])
        self.list_historical_questions = AsyncMock(return_value=[])
        self.find_by_request_id = AsyncMock(return_value=None)
        self.bind_request_id = AsyncMock()
        self.list_sessions = AsyncMock(return_value=[])
        self.find_by_resume_id = AsyncMock(return_value=[])
        self.find_by_session_id = AsyncMock(return_value=None)
        self.find_detail_by_session_id = AsyncMock(return_value=None)
        self.delete_by_session_id = AsyncMock()
        self.delete_by_resume_id = AsyncMock()
        self.find_unfinished_by_resume_id = AsyncMock(return_value=None)
        self.find_unfinished = AsyncMock(return_value=None)
        self.count_by_resume_id = AsyncMock(return_value=0)
        self.list_history_by_resume_id = AsyncMock(return_value=[])


class MockResumeRepository:
    def __init__(self):
        self.find_by_id = AsyncMock(return_value=None)
        self.update_status = AsyncMock()


class MockEvaluateMessageProducer:
    def __init__(self):
        self.send_evaluate_task = MagicMock()


class MockLlmService:
    def __init__(self):
        self.generate_response = AsyncMock(return_value="mock llm answer")


def build_mock_session_entity(session_id: str = "mock_session", resume_id: int = 1, status: str = "CREATED"):
    """使用 Entity Data 构建服务层返回的模拟结果"""
    from modules.interview.model.interview_entity import InterviewSessionEntity, SessionStatus
    from common.models import AsyncTaskStatus
    import datetime
    return InterviewSessionEntity(
        id=1,
        sessionId=session_id,
        resumeId=resume_id,
        totalQuestions=5,
        currentQuestionIndex=0,
        status=SessionStatus(status),
        questionsJson="[]",
        overallScore=0,
        overallFeedback="",
        strengthsJson="[]",
        improvementsJson="[]",
        referenceAnswersJson="[]",
        createdAt=datetime.datetime.now(),
        completedAt=None,
        evaluateStatus=AsyncTaskStatus.PENDING,
        evaluateError=None,
    )

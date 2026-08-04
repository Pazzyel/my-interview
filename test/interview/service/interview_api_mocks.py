import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.interview.model.interview_agent_dto import (
    CurrentQuestionResponse,
    InterviewQuestionDTO,
    InterviewSessionDTO,
    SubmitAnswerResponse,
)
from modules.interview.model.interview_dto import InterviewDetailDTO
from modules.interview.model.interview_entity import InterviewSessionEntity, SessionStatus


class MockInterviewAgentService:
    """该 Mock 替代了真实面试 Agent 服务（LLM 编排/评估），用于稳定返回面试流程数据。"""

    def __init__(self) -> None:
        question = InterviewQuestionDTO(
            question_index=1,
            question="请做一个简短自我介绍",
            type="JAVA_BASIC",
            category="基础",
        )
        session = InterviewSessionDTO(
            session_id="session-1",
            resume_text="mock resume",
            total_questions=1,
            current_question_index=0,
            questions=[question],
            status="CREATED",
            evaluate_status="PENDING",
            evaluate_error=None,
        )

        self.create_session = AsyncMock(return_value=session)
        self.list_sessions = AsyncMock(return_value=[])
        self.get_session = AsyncMock(return_value=session)
        self.get_current_question = AsyncMock(
            return_value=CurrentQuestionResponse(completed=False, message=None, question=question)
        )
        self.submit_answer = AsyncMock(
            return_value=SubmitAnswerResponse(has_next_question=False, next_question=None, current_index=1, total_questions=1)
        )
        self.save_answer = AsyncMock(return_value=None)
        self.complete_interview = AsyncMock(return_value=None)
        self.generate_report = AsyncMock(
            return_value={
                "overallScore": 90,
                "overallFeedback": "表现优秀",
                "strengths": ["表达清晰"],
                "improvements": ["补充细节"],
                "questionDetails": [],
                "referenceAnswers": [],
            }
        )
        self.export_report_pdf = AsyncMock(return_value=("report.pdf", b"%PDF-1.4"))


class MockInterviewHistoryService:
    """该 Mock 替代了真实面试历史查询服务，返回固定详情数据。"""

    def __init__(self) -> None:
        self.get_interview_detail = AsyncMock(
            return_value=InterviewDetailDTO(
                id=1,
                sessionId="session-1",
                totalQuestions=1,
                status="COMPLETED",
                evaluateStatus="COMPLETED",
                evaluateError=None,
                overallScore=90,
                overallFeedback="表现优秀",
                createdAt=datetime.now(),
                completedAt=datetime.now(),
                questions=[],
                strengths=["表达清晰"],
                improvements=["补充细节"],
                referenceAnswers=[],
                answers=[],
            )
        )


class MockInterviewPersistenceService:
    """该 Mock 替代了真实面试持久化服务，负责 unfinished 查询与删除调用记录。"""

    def __init__(self) -> None:
        self.find_unfinished_session_or_throw = AsyncMock(
            return_value=InterviewSessionEntity(
                id=1,
                sessionId="session-1",
                resumeId=1,
                totalQuestions=1,
                currentQuestionIndex=0,
                status=SessionStatus.CREATED,
                questionsJson="[]",
                overallScore=None,
                overallFeedback=None,
                strengthsJson=None,
                improvementsJson=None,
                referenceAnswersJson=None,
                createdAt=datetime.now(),
                completedAt=None,
                evaluateStatus="PENDING",
                evaluateError=None,
            )
        )
        self.delete_session_by_session_id = AsyncMock(return_value=None)


@dataclass
class InterviewApiTestContext:
    interview_agent_service: MockInterviewAgentService
    interview_history_service: MockInterviewHistoryService
    interview_persistence_service: MockInterviewPersistenceService


def create_interview_api_test_context() -> InterviewApiTestContext:
    return InterviewApiTestContext(
        interview_agent_service=MockInterviewAgentService(),
        interview_history_service=MockInterviewHistoryService(),
        interview_persistence_service=MockInterviewPersistenceService(),
    )

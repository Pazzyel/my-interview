"""
测试 InterviewAgentService 核心编排逻辑。
重点验证会话生命周期、各种参数透传以及状态流转逻辑。
"""
import sys
from pathlib import Path
import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from common.exceptions import BusinessException
from modules.interview.model.interview_agent_dto import (
    CreateInterviewRequest, SubmitAnswerRequest, InterviewQuestionDTO, InterviewReportDTO, QuestionEvaluationDTO
)
from modules.interview.model.interview_entity import SessionStatus
from modules.interview.service.interview_agent_service import InterviewAgentService
from common.models import AsyncTaskStatus
from interview_service_mocks import MockInterviewRepository, MockEvaluateMessageProducer, build_mock_session_entity


@pytest.fixture
def agent_service_env():
    repo = MockInterviewRepository()
    mq = MockEvaluateMessageProducer()
    service = InterviewAgentService(interview_repository=repo, evaluate_message_producer=mq)  # type: ignore

    # Mock internal sub-services to avoid LangGraph calls
    service.question_agent_service.generate_questions = AsyncMock(return_value=[
        InterviewQuestionDTO(question_index=0, question="Q1", type="JAVA_BASIC", category="Technical"),
        InterviewQuestionDTO(question_index=1, question="Q2", type="JAVA_CONCURRENT", category="HR")
    ])
    service.evaluation_agent_service.evaluate = AsyncMock(return_value=InterviewReportDTO(
        overall_score=80,
        overall_feedback="Good",
        strengths=["A"],
        improvements=["B"],
        reference_answers=[],
        question_details=[]
    ))
    return service, repo, mq


def test_create_session_success(agent_service_env):
    service, repo, _ = agent_service_env
    db = AsyncMock()
    req = CreateInterviewRequest(
        resume_id=1,
        resume_text="My Resume",
        question_count=3,
        force_create=True
    )
    repo.list_historical_questions.return_value = ["OldQ1"]

    result = asyncio.run(service.create_session(db, req))

    assert result.total_questions == 2
    assert len(result.questions) == 2
    assert result.status == SessionStatus.CREATED.value
    repo.create_session.assert_awaited_once()
    # 确认调用子服务生成问题
    service.question_agent_service.generate_questions.assert_awaited_once_with(
        resume_text="My Resume",
        question_count=3,
        historical_questions=["OldQ1"],
        session_id=ANY,
        skill_id="java-backend",
        difficulty=ANY,
        custom_categories=None,
        jd_text=None,
        llm_provider="default",
    )


def test_create_session_reuse_unfinished(agent_service_env):
    service, repo, _ = agent_service_env
    db = AsyncMock()
    # 模拟有未完成的会话
    mock_entity = build_mock_session_entity(session_id="unfinished-sess")
    repo.find_unfinished.return_value = mock_entity
    
    req = CreateInterviewRequest(resume_id=1, resume_text="My Resume", force_create=False)
    
    result = asyncio.run(service.create_session(db, req))

    # 返回复用的会话
    assert result.session_id == "unfinished-sess"
    # 没有生成新的
    repo.create_session.assert_not_awaited()


def test_create_session_request_id_is_idempotent(agent_service_env):
    service, repo, _ = agent_service_env
    db = AsyncMock()
    repo.find_by_request_id.return_value = build_mock_session_entity(session_id="idempotent-sess")

    result = asyncio.run(service.create_session(
        db,
        CreateInterviewRequest(request_id="request_1234", skill_id="java-backend"),
    ))

    assert result.session_id == "idempotent-sess"
    repo.create_session.assert_not_awaited()
    service.question_agent_service.generate_questions.assert_not_awaited()


def test_create_session_rejects_invalid_request_id(agent_service_env):
    service, _, _ = agent_service_env
    with pytest.raises(BusinessException):
        asyncio.run(service.create_session(
            AsyncMock(), CreateInterviewRequest(request_id="bad id", skill_id="java-backend")
        ))


def test_get_current_question_advance_status(agent_service_env):
    service, repo, _ = agent_service_env
    db = AsyncMock()
    # Mock return value of find_by_session_id
    mock_entity = build_mock_session_entity(status="CREATED", session_id="sess-start")
    mock_entity.questionsJson = '[{"question_index": 0, "question": "Q1", "type": "JAVA_BASIC", "category": "Tech"}]'
    repo.find_by_session_id.return_value = mock_entity

    result = asyncio.run(service.get_current_question(db, "sess-start"))

    assert result.completed is False
    assert result.question.question == "Q1"
    # 当首次访问问题时，状态应从 CREATED 更新为 IN_PROGRESS
    repo.update_session_status.assert_awaited_once_with(db, "sess-start", "IN_PROGRESS")


def test_submit_answer_has_next(agent_service_env):
    service, repo, mq = agent_service_env
    db = AsyncMock()
    # 2个问题，提交索引0
    mock_entity = build_mock_session_entity(status="IN_PROGRESS", session_id="sess")
    mock_entity.questionsJson = '[{"question_index": 0, "question": "Q1", "type": "JAVA_BASIC", "category": "Tech"}, {"question_index": 1, "question": "Q2", "type": "JAVA_CONCURRENT", "category": "HR"}]'
    repo.find_by_session_id.return_value = mock_entity

    req = SubmitAnswerRequest(question_index=0, answer="My Ans")
    result = asyncio.run(service.submit_answer(db, "sess", req))

    assert result.has_next_question is True
    assert result.current_index == 1
    repo.upsert_answer.assert_awaited_once()
    repo.update_session_progress.assert_awaited_once()
    mq.send_evaluate_task.assert_not_called()


def test_submit_answer_last_question(agent_service_env):
    service, repo, mq = agent_service_env
    db = AsyncMock()
    # 1个问题，提交索引0
    mock_entity = build_mock_session_entity(status="IN_PROGRESS", session_id="sess-last")
    mock_entity.questionsJson = '[{"question_index": 0, "question": "Q1", "type": "JAVA_BASIC", "category": "Tech"}]'
    repo.find_by_session_id.return_value = mock_entity

    req = SubmitAnswerRequest(question_index=0, answer="My Final Ans")
    result = asyncio.run(service.submit_answer(db, "sess-last", req))

    assert result.has_next_question is False
    # Completed,触发评估任务
    repo.update_evaluate_status.assert_awaited_with(db, "sess-last", "PENDING", None)
    mq.send_evaluate_task.assert_called_once_with("sess-last")


def test_complete_interview_forces_mq(agent_service_env):
    service, repo, mq = agent_service_env
    db = AsyncMock()
    mock_entity = build_mock_session_entity(status="IN_PROGRESS", session_id="sess-force")
    repo.find_by_session_id.return_value = mock_entity

    asyncio.run(service.complete_interview(db, "sess-force"))

    repo.update_session_status.assert_awaited_once_with(db, "sess-force", "COMPLETED")
    repo.update_evaluate_status.assert_awaited_once_with(db, "sess-force", "PENDING", None)
    mq.send_evaluate_task.assert_called_once_with("sess-force")


def test_generate_report_success(agent_service_env):
    service, repo, _ = agent_service_env
    db = AsyncMock()
    mock_entity = build_mock_session_entity(status="COMPLETED", session_id="sess-eval")
    repo.find_by_session_id.return_value = mock_entity

    report = asyncio.run(service.generate_report(db, "sess-eval"))

    assert report.overall_score == 80
    repo.save_report.assert_awaited_once()
    repo.update_session_status.assert_awaited_with(db, "sess-eval", "EVALUATED")
    repo.update_evaluate_status.assert_awaited_with(db, "sess-eval", "COMPLETED", None)


def test_export_report_pdf_valid(agent_service_env):
    from modules.interview.model.interview_dto import InterviewDetailDTO
    from datetime import datetime
    
    service, repo, _ = agent_service_env
    db = AsyncMock()
    
    dto = InterviewDetailDTO(
        id=1,
        sessionId="pdf-sess",
        totalQuestions=1,
        status="EVALUATED",
        evaluateStatus="COMPLETED",
        evaluateError=None,
        overallScore=90,
        overallFeedback="Excellent",
        createdAt=datetime.now(),
        completedAt=None,
        questions=[],
        strengths=["S1"],
        improvements=["I1"],
        referenceAnswers=[],
        answers=[]
    )
    repo.find_detail_by_session_id.return_value = dto

    filename, content = asyncio.run(service.export_report_pdf(db, "pdf-sess"))

    assert filename == "interview_report_pdf-sess.pdf"
    assert b"Excellent" in content
    assert b"S1" in content

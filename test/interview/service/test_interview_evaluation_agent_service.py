"""
测试 InterviewEvaluationAgentService 核心逻辑。
主要针对 LangGraph 具体 Node 进行单元测试，以规避网络请求同时保证分支覆盖。
"""
import sys
from pathlib import Path
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from modules.interview.model.interview_agent_dto import InterviewQuestionDTO, QuestionType
from modules.interview.service.interview_evaluation_agent_service import (
    InterviewEvaluationAgentService,
    InterviewEvaluateGraphState,
)
from modules.interview.model.interview_agent_llm_models import (
    InterviewEvaluationLLMItem
)


@pytest.fixture
def evaluate_service() -> InterviewEvaluationAgentService:
    return InterviewEvaluationAgentService()


def test_prepare_evaluate_context_valid(evaluate_service: InterviewEvaluationAgentService):
    q = InterviewQuestionDTO(question_index=0, question="Q", type=QuestionType.JAVA_BASIC, category="Tech")
    state = InterviewEvaluateGraphState(resume_text="Hello", questions=[q])
    result = asyncio.run(evaluate_service._node_prepare_evaluate_context(state))
    assert result.goto == "evaluate_answers"
    assert result.update["error_message"] is None


def test_prepare_evaluate_context_invalid(evaluate_service: InterviewEvaluationAgentService):
    state = InterviewEvaluateGraphState(resume_text="", questions=[])
    result = asyncio.run(evaluate_service._node_prepare_evaluate_context(state))
    assert result.goto == "fallback_report"
    assert result.update["error_message"] == "empty_questions"


@patch("modules.interview.service.interview_evaluation_agent_service.load_prompt")
def test_evaluate_answers_success(mock_load_prompt, evaluate_service: InterviewEvaluationAgentService):
    # Mock output
    class MockOutput:
        overall_score = 90
        overall_feedback = "Great job"
        strengths = ["S1"]
        improvements = ["I1"]
        question_evaluations = [
            InterviewEvaluationLLMItem(
                question_index=0, score=100, feedback="Perfect", reference_answer="Ref", key_points=["P1"]
            )
        ]
        
    class MockChain:
        async def ainvoke(self, *args, **kwargs):
            return MockOutput()
            
    # Mock pipe operator
    prompt_mock = AsyncMock()
    prompt_mock.__or__.return_value = MockChain()
    mock_load_prompt.return_value = prompt_mock

    evaluate_service._chat_model = MagicMock()
    
    q = InterviewQuestionDTO(question_index=0, question="Q1", type=QuestionType.JAVA_BASIC, category="Tech", user_answer="Ans")
    state = InterviewEvaluateGraphState(resume_text="Resume", questions=[q])
    
    result = asyncio.run(evaluate_service._node_evaluate_answers(state, config={"configurable": {"thread_id": "123"}}))
    
    assert result.goto == "__end__"
    report = result.update["report"]
    # 总分由逐题得分确定性计算，避免不同批次的模型总分漂移。
    assert report.overall_score == 100
    assert report.overall_feedback == "Great job"
    assert len(report.question_details) == 1
    assert report.question_details[0].score == 100
    assert report.question_details[0].feedback == "Perfect"
    assert report.reference_answers[0].reference_answer == "Ref"


@patch("modules.interview.service.interview_evaluation_agent_service.load_prompt")
def test_evaluate_answers_exception(mock_load_prompt, evaluate_service: InterviewEvaluationAgentService):
    class MockErrorChain:
        async def ainvoke(self, *args, **kwargs):
            raise ValueError("Evaluation Timeout")
            
    prompt_mock = AsyncMock()
    prompt_mock.__or__.return_value = MockErrorChain()
    mock_load_prompt.return_value = prompt_mock

    evaluate_service._chat_model = MagicMock()
    
    q = InterviewQuestionDTO(question_index=0, question="Q1", type=QuestionType.JAVA_BASIC, category="Tech")
    state = InterviewEvaluateGraphState(resume_text="Resume", questions=[q])
    
    result = asyncio.run(evaluate_service._node_evaluate_answers(state, config={"configurable": {"thread_id": "123"}}))
    
    assert result.goto == "fallback_report"
    assert "Evaluation Timeout" in result.update["error_message"]


def test_fallback_report(evaluate_service: InterviewEvaluationAgentService):
    q = InterviewQuestionDTO(question_index=0, question="Q1", type=QuestionType.JAVA_BASIC, category="Tech")
    state = InterviewEvaluateGraphState(resume_text="", questions=[q])
    
    result = asyncio.run(evaluate_service._node_fallback_report(state))
    
    assert result.goto == "__end__"
    report = result.update["report"]
    assert report.overall_score == 0
    assert report.question_details[0].score == 0
    assert report.question_details[0].feedback == "未作答，计 0 分"

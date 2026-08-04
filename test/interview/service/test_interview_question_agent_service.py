"""
测试 InterviewQuestionAgentService 的核心逻辑。
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

from modules.interview.model.interview_agent_dto import QuestionType
from modules.interview.service.interview_question_agent_service import (
    InterviewQuestionAgentService,
    InterviewQuestionGraphState,
)
from modules.interview.model.interview_agent_llm_models import InterviewQuestionLLMItem


@pytest.fixture
def question_service() -> InterviewQuestionAgentService:
    return InterviewQuestionAgentService()


def test_prepare_question_context_valid(question_service: InterviewQuestionAgentService):
    state = InterviewQuestionGraphState(resume_text="Hello", question_count=5)
    result = asyncio.run(question_service._node_prepare_question_context(state, config={}))
    assert result.goto == "generate_questions"
    assert result.update["error_message"] is None


def test_prepare_question_context_invalid(question_service: InterviewQuestionAgentService):
    state = InterviewQuestionGraphState(resume_text="", question_count=0)
    result = asyncio.run(question_service._node_prepare_question_context(state, config={}))
    assert result.goto == "fallback_questions"
    assert result.update["error_message"] == "invalid_input"


@patch("modules.interview.service.interview_question_agent_service.load_prompt")
def test_generate_questions_success(mock_load_prompt, question_service: InterviewQuestionAgentService):
    # Mock prompt
    mock_load_prompt.return_value = AsyncMock()
    
    # Mock chat model
    class MockOutput:
        questions = [
            InterviewQuestionLLMItem(question="LLM Q1", type="JAVA_BASIC", category="Tech", follow_ups=["F1"])
        ]
        
    class MockChain:
        async def ainvoke(self, *args, **kwargs):
            return MockOutput()
            
    # Mock pipe operator on prompt_template to return our chain
    prompt_mock = AsyncMock()
    prompt_mock.__or__.return_value = MockChain()
    mock_load_prompt.return_value = prompt_mock
    
    question_service._chat_model = MagicMock()
    
    state = InterviewQuestionGraphState(resume_text="Some resume", question_count=1)
    result = asyncio.run(question_service._node_generate_questions(state, config={"configurable": {"thread_id": "123"}}))
    
    assert result.goto == "normalize_questions"
    assert len(result.update["generated"]) == 1
    assert result.update["generated"][0].question == "LLM Q1"


@patch("modules.interview.service.interview_question_agent_service.load_prompt")
def test_generate_questions_exception(mock_load_prompt, question_service: InterviewQuestionAgentService):
    mock_load_prompt.return_value = AsyncMock()
    
    class MockErrorChain:
        async def ainvoke(self, *args, **kwargs):
            raise ValueError("Network Error")
            
    prompt_mock = AsyncMock()
    prompt_mock.__or__.return_value = MockErrorChain()
    mock_load_prompt.return_value = prompt_mock

    question_service._chat_model = MagicMock()
    
    state = InterviewQuestionGraphState(resume_text="Resume", question_count=1)
    result = asyncio.run(question_service._node_generate_questions(state, config={"configurable": {"thread_id": "123"}}))
    
    assert result.goto == "fallback_questions"
    assert "Network Error" in result.update["error_message"]


def test_normalize_questions_success(question_service: InterviewQuestionAgentService):
    item1 = InterviewQuestionLLMItem(
        question="Main Q1", type="JAVA_BASIC", category="Tech", follow_ups=["Follow Q1"]
    )
    state = InterviewQuestionGraphState(
        resume_text="", question_count=1, generated=[item1]
    )
    
    result = asyncio.run(question_service._node_normalize_questions(state))
    
    questions = result.update["questions"]
    assert len(questions) == 2  # 1 main + 1 followup
    # First is main question
    assert questions[0].question == "Main Q1"
    assert questions[0].is_follow_up is False
    assert questions[0].question_index == 0
    # Second is follow up
    assert questions[1].question == "Follow Q1"
    assert questions[1].is_follow_up is True
    assert questions[1].parent_question_index == 0
    assert questions[1].question_index == 1


def test_fallback_questions(question_service: InterviewQuestionAgentService):
    state = InterviewQuestionGraphState(resume_text="", question_count=2)
    result = asyncio.run(question_service._node_fallback_questions(state))
    
    questions = result.update["questions"]
    # 每道主问题都带一条追问，因此线性题目列表包含 2 主问 + 2 追问。
    assert len(questions) == 4
    assert questions[0].is_follow_up is False
    assert questions[1].is_follow_up is True

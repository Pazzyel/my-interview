"""
测试 InterviewEvaluateConsumerService
"""
import sys
from pathlib import Path
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from modules.interview.service.interview_evaluate_consumer_service import InterviewEvaluateConsumerService
from interview_service_mocks import MockInterviewRepository, build_mock_session_entity


@pytest.fixture
def consumer_env():
    repo = MockInterviewRepository()
    agent_service = AsyncMock()
    service = InterviewEvaluateConsumerService(agent_service, repo)  # type: ignore
    return service, agent_service, repo


class MockSession:
    def __init__(self):
        self.db = AsyncMock()
        
    async def __aenter__(self):
        return self.db
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@patch("modules.interview.service.interview_evaluate_consumer_service.async_session_factory")
def test_process_task_session_not_found(mock_factory, consumer_env):
    mock_factory.return_value = MockSession()
    service, agent_service, repo = consumer_env
    repo.find_by_session_id.return_value = None
    
    asyncio.run(service.process_task("not-found"))
    
    repo.find_by_session_id.assert_awaited_once()
    agent_service.generate_report.assert_not_called()


@patch("modules.interview.service.interview_evaluate_consumer_service.async_session_factory")
def test_process_task_success(mock_factory, consumer_env):
    mock_factory.return_value = MockSession()
    service, agent_service, repo = consumer_env
    entity = build_mock_session_entity()
    repo.find_by_session_id.return_value = entity
    
    asyncio.run(service.process_task("sess-1"))
    
    repo.find_by_session_id.assert_awaited_once()
    agent_service.generate_report.assert_awaited_once()
    assert agent_service.generate_report.call_args[0][1] == "sess-1"


@patch("modules.interview.service.interview_evaluate_consumer_service.async_session_factory")
def test_mark_failed(mock_factory, consumer_env):
    mock_factory.return_value = MockSession()
    service, agent_service, repo = consumer_env
    
    asyncio.run(service.mark_failed("sess-fail", "some error"))
    
    repo.update_evaluate_status.assert_awaited_once()
    assert repo.update_evaluate_status.call_args[0][1] == "sess-fail"
    assert repo.update_evaluate_status.call_args[0][2] == "FAILED"
    assert repo.update_evaluate_status.call_args[0][3] == "some error"

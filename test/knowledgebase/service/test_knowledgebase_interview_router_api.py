from datetime import datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.interview.model.interview_agent_dto import InterviewSessionDTO
from modules.knowledgebase.model.knowledgebase_question import (
    CategoryCount,
    InterviewCategoryCapacity,
    InterviewFollowUpCapacity,
    KnowledgeBaseInterviewCapacityResponse,
    KnowledgeBaseQuestionDTO,
    KnowledgeBaseQuestionStatus,
    QuestionGenStatus,
    QuestionGenStatusResponse,
)
from api_test_fixture import load_router_module

router_module = load_router_module(
    "modules.knowledgebase.router.knowledgebase_interview_router",
    dependency_fields=["knowledgebase_question_service", "knowledgebase_interview_service"],
)


def test_all_knowledgebase_interview_routes_follow_frontend_contract() -> None:
    question = KnowledgeBaseQuestionDTO(
        id=7, knowledgeBaseId=1, knowledgeBaseName="KB", category="Redis", question="Q",
        status=KnowledgeBaseQuestionStatus.DRAFT, createdAt=datetime.now(), updatedAt=datetime.now(),
    )
    question_service = AsyncMock()
    question_service.list_questions.return_value = [question]
    question_service.list_categories.return_value = [CategoryCount(category="Redis", count=1)]
    question_service.submit_generation_task.return_value = QuestionGenStatusResponse(
        knowledgeBaseId=1, questionGenStatus=QuestionGenStatus.QUEUED, questionGenTaskId="task"
    )
    question_service.get_generation_status.return_value = QuestionGenStatusResponse(
        knowledgeBaseId=1, questionGenStatus=QuestionGenStatus.COMPLETED, savedCount=1
    )
    question_service.create_question.return_value = question
    question_service.update_question.return_value = question
    question_service.update_status.return_value = question

    interview_service = AsyncMock()
    interview_service.get_capacity.return_value = KnowledgeBaseInterviewCapacityResponse(
        knowledgeBaseId=1, category=None, difficulty="mid", mainQuestionCount=1,
        categories=[InterviewCategoryCapacity(category="Redis", availableQuestionCount=1)],
        followUpOptions=[InterviewFollowUpCapacity(
            followUpCount=0, availableQuestionCount=1, selectable=True
        )],
    )
    interview_service.create_session.return_value = InterviewSessionDTO(
        sessionId="session", resumeText="", totalQuestions=1, currentQuestionIndex=0,
        questions=[], status="CREATED", knowledgeBaseId=1,
    )
    router_module.knowledgebase_question_service = question_service
    router_module.knowledgebase_interview_service = interview_service

    async def override_db():
        yield object()

    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.get_async_session] = override_db
    with TestClient(app) as client:
        responses = [
            client.get("/api/knowledgebase/1/questions?category=Redis"),
            client.get("/api/knowledgebase/1/questions/categories"),
            client.post("/api/knowledgebase/1/questions/generate", json={"questionCount": 5}),
            client.get("/api/knowledgebase/1/questions/generation-status"),
            client.post("/api/knowledgebase/1/questions", json={"category": "Redis", "question": "Q"}),
            client.put("/api/knowledgebase/questions/7", json={"question": "Q2"}),
            client.put("/api/knowledgebase/questions/7/status", json={"status": "ACTIVE"}),
            client.delete("/api/knowledgebase/questions/7"),
            client.get("/api/knowledgebase/1/interview-capacity?difficulty=mid&mainQuestionCount=1"),
            client.post("/api/knowledgebase-interviews/sessions", json={
                "knowledgeBaseId": 1, "difficulty": "mid", "mainQuestionCount": 1,
                "followUpCount": 0,
            }),
        ]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["data"][0]["knowledgeBaseId"] == 1
    assert responses[2].json()["data"]["questionGenStatus"] == "QUEUED"
    assert responses[8].json()["data"]["followUpOptions"][0]["selectable"] is True
    assert responses[9].json()["data"]["knowledgeBaseId"] == 1

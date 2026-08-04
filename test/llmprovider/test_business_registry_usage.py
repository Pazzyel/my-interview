import asyncio

from modules.interview.service.interview_evaluation_agent_service import InterviewEvaluationAgentService
from modules.interview.service.interview_question_agent_service import InterviewQuestionAgentService
from modules.interview.service.interview_skill_service import InterviewSkillService
from modules.resume.service.resume_grading_service import ResumeGradingService


class FakeRegistry:
    def __init__(self):
        self.calls = []
        self.model = object()

    async def resolve(self, provider):
        self.calls.append(provider)
        return self.model


def test_interview_question_and_evaluation_use_requested_provider():
    async def scenario():
        registry = FakeRegistry()
        question = InterviewQuestionAgentService(llm_provider_resolver=registry)
        evaluation = InterviewEvaluationAgentService(registry)
        assert await question._model("provider-a") is registry.model
        assert await evaluation._model("provider-a") is registry.model
        assert registry.calls == ["provider-a", "provider-a"]
    asyncio.run(scenario())


def test_jd_and_resume_services_use_default_provider():
    async def scenario():
        registry = FakeRegistry()
        skill = InterviewSkillService(llm_provider_resolver=registry)
        resume = ResumeGradingService(registry)
        assert await skill._get_chat_model() is registry.model
        assert resume._llm_provider_resolver is registry
        assert registry.calls == [None]
    asyncio.run(scenario())

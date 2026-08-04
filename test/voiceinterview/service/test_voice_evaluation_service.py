import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.models import AsyncTaskStatus
from infrastructure.database.models import Base
from modules.interview.model.interview_agent_dto import (
    InterviewReportDTO,
    QuestionEvaluationDTO,
    ReferenceAnswerDTO,
)
from modules.voiceinterview.model.voice_interview_dto import CreateVoiceInterviewRequest
from modules.voiceinterview.model.voice_interview_entity import InterviewPhase
from modules.voiceinterview.repository.evaluation_repository import VoiceInterviewEvaluationRepository
from modules.voiceinterview.repository.message_repository import VoiceInterviewMessageRepository
from modules.voiceinterview.repository.session_repository import VoiceInterviewSessionRepository
from modules.voiceinterview.service.evaluation_service import VoiceInterviewEvaluationService
from modules.voiceinterview.service.session_service import VoiceInterviewSessionService


class _ResumeRepository:
    async def find_by_id(self, db, resume_id):
        del db, resume_id
        return None


class _SkillService:
    def build_evaluation_reference_section_safe(self, skill_id):
        return f"reference:{skill_id}"


class _Evaluator:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    async def evaluate(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("mock evaluation failed")
        question = kwargs["questions"][0]
        return InterviewReportDTO(
            sessionId=kwargs["session_id"], totalQuestions=1, overallScore=88,
            overallFeedback="整体表现良好", strengths=["表达清晰"], improvements=["补充边界条件"],
            questionDetails=[QuestionEvaluationDTO(
                questionIndex=1, question=question.question, category=question.category,
                userAnswer=question.user_answer, score=88, feedback="回答正确",
            )],
            referenceAnswers=[ReferenceAnswerDTO(
                questionIndex=1, question=question.question,
                referenceAnswer="参考答案", keyPoints=["关键点"],
            )],
        )


async def _prepare(maker):
    sessions = VoiceInterviewSessionRepository()
    messages = VoiceInterviewMessageRepository()
    evaluations = VoiceInterviewEvaluationRepository()
    service = VoiceInterviewSessionService(sessions, messages, evaluations)
    async with maker() as db:
        created = await service.create_session(
            db, CreateVoiceInterviewRequest(skillId="python-backend"), "ws://test/{session_id}"
        )
        await messages.append_ai_question(db, created.session_id, InterviewPhase.TECH, "解释 asyncio")
        await messages.fill_latest_unanswered(db, created.session_id, "协作式并发")
        await db.commit()
        await service.end_session(db, created.session_id)
    return created.session_id, sessions, messages, evaluations


def test_evaluation_success_duplicate_and_missing_session(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'evaluation.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session_id, sessions, messages, evaluations = await _prepare(maker)
        evaluator = _Evaluator()
        service = VoiceInterviewEvaluationService(
            maker, sessions, messages, evaluations, _ResumeRepository(), evaluator, _SkillService()
        )
        await service.process(session_id)
        await service.process(session_id)
        await service.process(999999)
        assert evaluator.calls == 1
        async with maker() as db:
            session = await sessions.find_by_id(db, session_id)
            detail = await evaluations.get_detail(db, session_id)
            assert session.evaluate_status == AsyncTaskStatus.COMPLETED
            assert detail.overall_score == 88
            assert detail.answers[0]["referenceAnswer"] == "参考答案"
        await engine.dispose()
    asyncio.run(scenario())


def test_evaluation_failure_marks_failed(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'failed.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session_id, sessions, messages, evaluations = await _prepare(maker)
        service = VoiceInterviewEvaluationService(
            maker, sessions, messages, evaluations, _ResumeRepository(), _Evaluator(True), _SkillService()
        )
        try:
            await service.process(session_id)
        except RuntimeError:
            pass
        async with maker() as db:
            session = await sessions.find_by_id(db, session_id)
            assert session.evaluate_status == AsyncTaskStatus.FAILED
            assert "mock evaluation failed" in session.evaluate_error
        await engine.dispose()
    asyncio.run(scenario())

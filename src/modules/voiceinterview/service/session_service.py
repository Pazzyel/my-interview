import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from common.models import AsyncTaskStatus
from modules.voiceinterview.model.voice_interview_dto import (
    CreateVoiceInterviewRequest, SessionMetaDTO, SessionResponseDTO,
    VoiceEvaluationStatusDTO, VoiceInterviewMessageDTO,
)
from modules.voiceinterview.model.voice_interview_entity import (
    InterviewPhase, VoiceInterviewSessionEntity, VoiceInterviewSessionStatus,
)
from modules.voiceinterview.repository.evaluation_repository import VoiceInterviewEvaluationRepository
from modules.voiceinterview.repository.message_repository import VoiceInterviewMessageRepository
from modules.voiceinterview.repository.session_repository import VoiceInterviewSessionRepository
from modules.resume.repository.resume_repository import ResumeRepository
from modules.interview.service.interview_skill_service import InterviewSkillService

EvaluationPublisher = Callable[[int], Awaitable[object] | object]


class VoiceInterviewSessionService:
    def __init__(
        self,
        session_repository: VoiceInterviewSessionRepository | None = None,
        message_repository: VoiceInterviewMessageRepository | None = None,
        evaluation_repository: VoiceInterviewEvaluationRepository | None = None,
        evaluation_publisher: EvaluationPublisher | None = None,
        resume_repository: ResumeRepository | None = None,
        skill_service: InterviewSkillService | None = None,
        processing_stale_seconds: int = 600,
    ) -> None:
        self.sessions = session_repository or VoiceInterviewSessionRepository()
        self.messages = message_repository or VoiceInterviewMessageRepository()
        self.evaluations = evaluation_repository or VoiceInterviewEvaluationRepository()
        self.evaluation_publisher = evaluation_publisher
        self.resume_repository = resume_repository
        self.skill_service = skill_service
        self.processing_stale_seconds = max(1, processing_stale_seconds)

    async def create_session(
        self, db: AsyncSession, request: CreateVoiceInterviewRequest, web_socket_url: str
    ) -> SessionResponseDTO:
        if self.skill_service is not None:
            self.skill_service.get_skill(request.skill_id)
        if (
            request.resume_id is not None
            and self.resume_repository is not None
            and not await self.resume_repository.exists_by_id(db, request.resume_id)
        ):
            raise BusinessException(ErrorCode.BAD_REQUEST, f"Resume not found: {request.resume_id}")
        phase = self._first_enabled_phase(request)
        now = datetime.now()
        role_type = request.role_type or request.skill_id
        entity = VoiceInterviewSessionEntity(
            user_id=request.user_id, role_type=role_type, skill_id=request.skill_id,
            difficulty=request.difficulty, custom_jd_text=request.custom_jd_text,
            resume_id=request.resume_id, intro_enabled=request.intro_enabled,
            tech_enabled=request.tech_enabled, project_enabled=request.project_enabled,
            hr_enabled=request.hr_enabled, llm_provider=request.llm_provider,
            current_phase=phase, planned_duration=request.planned_duration,
            start_time=now, created_at=now, updated_at=now,
        )
        saved = await self.sessions.save(db, entity)
        await db.commit()
        return self._response(saved, web_socket_url.format(session_id=saved.id))

    async def get_session(self, db: AsyncSession, session_id: int) -> VoiceInterviewSessionEntity:
        session = await self.sessions.find_by_id(db, session_id)
        if session is None:
            raise BusinessException(ErrorCode.NOT_FOUND, f"Voice interview session not found: {session_id}")
        return session

    async def get_session_dto(
        self, db: AsyncSession, session_id: int, web_socket_url: str
    ) -> SessionResponseDTO:
        return self._response(await self.get_session(db, session_id), web_socket_url.format(session_id=session_id))

    async def list_sessions(
        self, db: AsyncSession, user_id: str | None = None, status: str | None = None
    ) -> list[SessionMetaDTO]:
        parsed_status = None
        if status and status.strip():
            try:
                parsed_status = VoiceInterviewSessionStatus(status.strip().upper())
            except ValueError as exc:
                raise BusinessException(ErrorCode.BAD_REQUEST, f"Invalid voice interview status: {status}") from exc
        return await self.sessions.list_sessions(db, user_id, parsed_status)

    async def pause_session(self, db: AsyncSession, session_id: int) -> None:
        session = await self.get_session(db, session_id)
        if session.status != VoiceInterviewSessionStatus.IN_PROGRESS:
            raise BusinessException(ErrorCode.BAD_REQUEST, "Only an in-progress session can be paused")
        await self.sessions.update_fields(db, session_id, status=VoiceInterviewSessionStatus.PAUSED,
                                          paused_at=datetime.now())
        await db.commit()

    async def resume_session(
        self, db: AsyncSession, session_id: int, web_socket_url: str
    ) -> SessionResponseDTO:
        session = await self.get_session(db, session_id)
        if session.status != VoiceInterviewSessionStatus.PAUSED:
            raise BusinessException(ErrorCode.BAD_REQUEST, "Only a paused session can be resumed")
        now = datetime.now()
        paused_seconds = max(0, int((now - session.paused_at).total_seconds())) if session.paused_at else 0
        await self.sessions.update_fields(
            db, session_id, status=VoiceInterviewSessionStatus.IN_PROGRESS, resumed_at=now,
            paused_at=None, total_paused_seconds=session.total_paused_seconds + paused_seconds,
        )
        await db.commit()
        return await self.get_session_dto(db, session_id, web_socket_url)

    async def end_session(self, db: AsyncSession, session_id: int) -> None:
        session = await self.get_session(db, session_id)
        if session.status == VoiceInterviewSessionStatus.COMPLETED:
            return
        if session.status not in (VoiceInterviewSessionStatus.IN_PROGRESS, VoiceInterviewSessionStatus.PAUSED):
            raise BusinessException(ErrorCode.BAD_REQUEST, "Session cannot be completed from its current state")
        now = datetime.now()
        total_paused = session.total_paused_seconds
        if session.status == VoiceInterviewSessionStatus.PAUSED and session.paused_at:
            total_paused += max(0, int((now - session.paused_at).total_seconds()))
        actual_duration = max(0, int((now - session.start_time).total_seconds()) - total_paused)
        await self.sessions.update_fields(
            db, session_id, status=VoiceInterviewSessionStatus.COMPLETED,
            current_phase=InterviewPhase.COMPLETED, end_time=now, actual_duration=actual_duration,
            total_paused_seconds=total_paused, paused_at=None,
            evaluate_status=AsyncTaskStatus.PENDING, evaluate_error=None,
        )
        # The task must never become visible before COMPLETED/PENDING is committed.
        await db.commit()
        await self._publish(session_id)

    async def delete_session(self, db: AsyncSession, session_id: int) -> None:
        if not await self.sessions.delete(db, session_id):
            raise BusinessException(ErrorCode.NOT_FOUND, f"Voice interview session not found: {session_id}")
        await db.commit()

    async def start_phase(self, db: AsyncSession, session_id: int, phase: InterviewPhase | str) -> InterviewPhase:
        session = await self.get_session(db, session_id)
        if session.status != VoiceInterviewSessionStatus.IN_PROGRESS:
            raise BusinessException(ErrorCode.BAD_REQUEST, "Phase can only change while the session is in progress")
        try:
            target = phase if isinstance(phase, InterviewPhase) else InterviewPhase(str(phase).upper())
        except ValueError as exc:
            raise BusinessException(ErrorCode.BAD_REQUEST, f"Invalid interview phase: {phase}") from exc
        order = [InterviewPhase.INTRO, InterviewPhase.TECH, InterviewPhase.PROJECT, InterviewPhase.HR]
        enabled = {
            InterviewPhase.INTRO: session.intro_enabled, InterviewPhase.TECH: session.tech_enabled,
            InterviewPhase.PROJECT: session.project_enabled, InterviewPhase.HR: session.hr_enabled,
        }
        if target == InterviewPhase.COMPLETED or not enabled.get(target, False):
            raise BusinessException(ErrorCode.BAD_REQUEST, f"Interview phase is not enabled: {target.value}")
        if order.index(target) < order.index(session.current_phase):
            raise BusinessException(ErrorCode.BAD_REQUEST, "Interview phase cannot move backwards")
        await self.sessions.update_fields(db, session_id, current_phase=target)
        await db.commit()
        return target

    async def get_messages(self, db: AsyncSession, session_id: int) -> list[VoiceInterviewMessageDTO]:
        await self.get_session(db, session_id)
        return await self.messages.list_public(db, session_id)

    async def get_evaluation(self, db: AsyncSession, session_id: int) -> VoiceEvaluationStatusDTO:
        session = await self.get_session(db, session_id)
        detail = None
        if session.evaluate_status == AsyncTaskStatus.COMPLETED:
            detail = await self.evaluations.get_detail(db, session_id)
        return VoiceEvaluationStatusDTO(
            evaluate_status=session.evaluate_status.value if session.evaluate_status else None,
            evaluate_error=session.evaluate_error, evaluate_status_updated_at=session.updated_at,
            evaluation=detail,
        )

    async def trigger_evaluation(self, db: AsyncSession, session_id: int) -> VoiceEvaluationStatusDTO:
        session = await self.get_session(db, session_id)
        if session.status != VoiceInterviewSessionStatus.COMPLETED:
            raise BusinessException(ErrorCode.BAD_REQUEST, "Evaluation requires a completed session")
        if session.evaluate_status == AsyncTaskStatus.COMPLETED:
            return await self.get_evaluation(db, session_id)
        processing_is_stale = (
            session.evaluate_status == AsyncTaskStatus.PROCESSING
            and session.updated_at < datetime.now() - timedelta(seconds=self.processing_stale_seconds)
        )
        if session.evaluate_status != AsyncTaskStatus.PROCESSING or processing_is_stale:
            await self.sessions.update_fields(
                db, session_id, evaluate_status=AsyncTaskStatus.PENDING, evaluate_error=None
            )
            await db.commit()
            await self._publish(session_id)
        return await self.get_evaluation(db, session_id)

    async def _publish(self, session_id: int) -> None:
        if self.evaluation_publisher is None:
            return
        result = self.evaluation_publisher(session_id)
        if inspect.isawaitable(result):
            await result

    @staticmethod
    def _first_enabled_phase(request: CreateVoiceInterviewRequest) -> InterviewPhase:
        for phase, enabled in (
            (InterviewPhase.INTRO, request.intro_enabled), (InterviewPhase.TECH, request.tech_enabled),
            (InterviewPhase.PROJECT, request.project_enabled), (InterviewPhase.HR, request.hr_enabled),
        ):
            if enabled:
                return phase
        raise BusinessException(ErrorCode.BAD_REQUEST, "At least one interview phase must be enabled")

    @staticmethod
    def _response(session: VoiceInterviewSessionEntity, web_socket_url: str) -> SessionResponseDTO:
        return SessionResponseDTO(
            session_id=session.id or 0, user_id=session.user_id, role_type=session.role_type,
            skill_id=session.skill_id, difficulty=session.difficulty,
            current_phase=session.current_phase.value, status=session.status.value,
            start_time=session.start_time, planned_duration=session.planned_duration,
            actual_duration=session.actual_duration, web_socket_url=web_socket_url,
        )

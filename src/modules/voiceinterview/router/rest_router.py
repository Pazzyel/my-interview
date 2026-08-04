import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.voiceinterview.model.voice_interview_dto import (
    CreateVoiceInterviewRequest, PauseVoiceInterviewRequest, SessionMetaDTO, SessionResponseDTO,
    VoiceEvaluationStatusDTO, VoiceInterviewMessageDTO,
)
from modules.voiceinterview.service.session_service import VoiceInterviewSessionService
from modules.voiceinterview.realtime.manager import VoiceInterviewRuntimeManager

router = APIRouter(prefix="/api/voice-interview", tags=["Voice Interview"])
voice_interview_session_service = VoiceInterviewSessionService()
voice_runtime_manager: VoiceInterviewRuntimeManager | None = None


def configure_runtime_manager(manager: VoiceInterviewRuntimeManager) -> None:
    global voice_runtime_manager
    voice_runtime_manager = manager


def _web_socket_template(request: Request) -> str:
    configured_base = (getattr(app_config, "voice_public_ws_base_url", None) or "").strip().rstrip("/")
    if configured_base:
        parsed_base = urlsplit(configured_base)
        if parsed_base.scheme not in {"ws", "wss"} or not parsed_base.netloc:
            raise BusinessException(ErrorCode.INTERNAL_ERROR, "VOICE_PUBLIC_WS_BASE_URL 配置无效")
        return f"{configured_base}/ws/voice-interview/{{session_id}}"

    forwarded_proto = ""
    forwarded_host = ""
    if getattr(app_config, "voice_trust_forwarded_headers", False):
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    scheme = forwarded_proto or request.url.scheme
    ws_scheme = "wss" if scheme == "https" else "ws"
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    if re.fullmatch(r"[A-Za-z0-9.\-\[\]:]+", host) is None:
        raise BusinessException(ErrorCode.BAD_REQUEST, "Invalid Host header")
    hostname = (urlsplit(f"//{host}").hostname or "").lower()
    configured_hosts = getattr(app_config, "voice_allowed_hosts", ["localhost", "127.0.0.1", "testserver"])
    allowed_hosts = {item.strip().lower() for item in configured_hosts if item.strip()}
    if hostname not in allowed_hosts:
        raise BusinessException(ErrorCode.BAD_REQUEST, "Untrusted Host header")
    return f"{ws_scheme}://{host}/ws/voice-interview/{{session_id}}"


@router.post("/sessions", response_model=Result[SessionResponseDTO])
async def create_session(request_body: CreateVoiceInterviewRequest, request: Request,
                         db: AsyncSession = Depends(get_async_session)) -> Result[SessionResponseDTO]:
    result = await voice_interview_session_service.create_session(db, request_body, _web_socket_template(request))
    return Result.success(result)


@router.get("/sessions", response_model=Result[list[SessionMetaDTO]])
async def list_sessions(userId: str | None = None, status: str | None = None,
                        db: AsyncSession = Depends(get_async_session)) -> Result[list[SessionMetaDTO]]:
    return Result.success(await voice_interview_session_service.list_sessions(db, userId, status))


@router.get("/sessions/{session_id}", response_model=Result[SessionResponseDTO])
async def get_session(session_id: int, request: Request,
                      db: AsyncSession = Depends(get_async_session)) -> Result[SessionResponseDTO]:
    return Result.success(await voice_interview_session_service.get_session_dto(
        db, session_id, _web_socket_template(request)))


@router.put("/sessions/{session_id}/pause", response_model=Result[None])
async def pause_session(session_id: int, request_body: PauseVoiceInterviewRequest,
                        db: AsyncSession = Depends(get_async_session)) -> Result[None]:
    await voice_interview_session_service.pause_session(db, session_id)
    if voice_runtime_manager is not None:
        await voice_runtime_manager.close_session(session_id, "interview paused")
    return Result.success()


@router.put("/sessions/{session_id}/resume", response_model=Result[SessionResponseDTO])
async def resume_session(session_id: int, request: Request,
                         db: AsyncSession = Depends(get_async_session)) -> Result[SessionResponseDTO]:
    return Result.success(await voice_interview_session_service.resume_session(
        db, session_id, _web_socket_template(request)))


@router.post("/sessions/{session_id}/end", response_model=Result[None])
async def end_session(session_id: int, db: AsyncSession = Depends(get_async_session)) -> Result[None]:
    await voice_interview_session_service.end_session(db, session_id)
    if voice_runtime_manager is not None:
        await voice_runtime_manager.close_session(session_id, "interview ended")
    return Result.success()


@router.delete("/sessions/{session_id}", response_model=Result[None])
async def delete_session(session_id: int, db: AsyncSession = Depends(get_async_session)) -> Result[None]:
    await voice_interview_session_service.delete_session(db, session_id)
    if voice_runtime_manager is not None:
        await voice_runtime_manager.close_session(session_id, "interview deleted")
    return Result.success()


@router.get("/sessions/{session_id}/messages", response_model=Result[list[VoiceInterviewMessageDTO]])
async def get_messages(session_id: int, db: AsyncSession = Depends(get_async_session)) -> Result[list[VoiceInterviewMessageDTO]]:
    return Result.success(await voice_interview_session_service.get_messages(db, session_id))


@router.get("/sessions/{session_id}/evaluation", response_model=Result[VoiceEvaluationStatusDTO])
async def get_evaluation(session_id: int, db: AsyncSession = Depends(get_async_session)) -> Result[VoiceEvaluationStatusDTO]:
    return Result.success(await voice_interview_session_service.get_evaluation(db, session_id))


@router.post("/sessions/{session_id}/evaluation", response_model=Result[VoiceEvaluationStatusDTO])
async def trigger_evaluation(session_id: int, db: AsyncSession = Depends(get_async_session)) -> Result[VoiceEvaluationStatusDTO]:
    return Result.success(await voice_interview_session_service.trigger_evaluation(db, session_id))

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.connection import get_async_session
from modules.voiceinterview.realtime.manager import VoiceInterviewRuntimeManager


_runtime_manager: VoiceInterviewRuntimeManager | None = None


def configure_runtime_manager(manager: VoiceInterviewRuntimeManager) -> None:
    global _runtime_manager
    _runtime_manager = manager


def create_websocket_router(manager: VoiceInterviewRuntimeManager) -> APIRouter:
    configured = APIRouter(tags=["Voice Interview WebSocket"])

    @configured.websocket("/ws/voice-interview/{session_id}")
    async def voice_interview_websocket(
        websocket: WebSocket,
        session_id: int,
        db: Annotated[AsyncSession, Depends(get_async_session)],
    ) -> None:
        await manager.handle(websocket, session_id, db)

    return configured


router = APIRouter(tags=["Voice Interview WebSocket"])


@router.websocket("/ws/voice-interview/{session_id}")
async def voice_interview_websocket(
    websocket: WebSocket,
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    if _runtime_manager is None:
        await websocket.close(code=1011, reason="voice interview runtime is not configured")
        return
    await _runtime_manager.handle(websocket, session_id, db)

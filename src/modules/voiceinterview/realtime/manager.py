from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import WebSocket

from modules.voiceinterview.speech.protocols import AsrProvider, TtsProvider

from .protocols import ConversationServiceProtocol, SessionServiceProtocol
from .runtime import VoiceInterviewRuntime


class VoiceInterviewRuntimeManager:
    def __init__(
        self,
        *,
        session_service: SessionServiceProtocol,
        conversation_service: ConversationServiceProtocol,
        asr_provider: AsrProvider,
        tts_provider: TtsProvider,
        cooldown_ms: int = 800,
        tts_concurrency: int = 3,
        max_asr_reconnects: int = 2,
    ) -> None:
        self.session_service = session_service
        self.conversation_service = conversation_service
        self.asr_provider = asr_provider
        self.tts_provider = tts_provider
        self.cooldown_ms = cooldown_ms
        self.tts_concurrency = tts_concurrency
        self.max_asr_reconnects = max_asr_reconnects
        self._runtimes: dict[int, VoiceInterviewRuntime] = {}
        self._lock = asyncio.Lock()

    async def handle(self, websocket: WebSocket, session_id: int, db: Any) -> None:
        try:
            session = await self.session_service.get_session(db, session_id)
            status = getattr(session, "status", None)
            status_value = getattr(status, "value", status)
            if status_value != "IN_PROGRESS":
                await websocket.close(code=1008, reason="interview session is not in progress")
                return
        except Exception as exc:
            await websocket.close(code=1008, reason=str(exc)[:120] or "interview session not found")
            return

        runtime = VoiceInterviewRuntime(
            websocket=websocket,
            session_id=session_id,
            db=db,
            session=session,
            asr_provider=self.asr_provider,
            tts_provider=self.tts_provider,
            conversation_service=self.conversation_service,
            session_service=self.session_service,
            cooldown_ms=self.cooldown_ms,
            tts_concurrency=self.tts_concurrency,
            max_asr_reconnects=self.max_asr_reconnects,
        )
        async with self._lock:
            previous = self._runtimes.get(session_id)
            self._runtimes[session_id] = runtime
        if previous is not None:
            await previous.close(code=1000, reason="replaced by a newer connection")
        try:
            await runtime.run()
        except Exception as exc:
            if not runtime.closed:
                with contextlib.suppress(Exception):
                    await runtime.send_error(str(exc))
        finally:
            await runtime.close()
            async with self._lock:
                if self._runtimes.get(session_id) is runtime:
                    self._runtimes.pop(session_id, None)

    async def close_all(self) -> None:
        async with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        await asyncio.gather(
            *(runtime.close(code=1001, reason="server shutdown") for runtime in runtimes),
            return_exceptions=True,
        )

    async def close_session(self, session_id: int, reason: str = "session state changed") -> None:
        async with self._lock:
            runtime = self._runtimes.pop(session_id, None)
        if runtime is not None:
            await runtime.close(code=1000, reason=reason)

    def active_session_ids(self) -> tuple[int, ...]:
        return tuple(self._runtimes)

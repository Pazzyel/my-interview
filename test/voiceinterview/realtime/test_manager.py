import asyncio
from types import SimpleNamespace

from starlette.websockets import WebSocketState

from modules.voiceinterview.realtime.manager import VoiceInterviewRuntimeManager


class FakeSocket:
    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTING
        self.closed = None

    async def close(self, code=1000, reason="") -> None:
        self.closed = (code, reason)
        self.application_state = WebSocketState.DISCONNECTED


class SessionService:
    def __init__(self, status="IN_PROGRESS") -> None:
        self.status = status

    async def get_session(self, _db, _session_id):
        return SimpleNamespace(status=self.status)


def manager(status="IN_PROGRESS") -> VoiceInterviewRuntimeManager:
    return VoiceInterviewRuntimeManager(
        session_service=SessionService(status),
        conversation_service=object(),
        asr_provider=object(),
        tts_provider=object(),
    )


def test_completed_or_paused_session_is_rejected_before_accept() -> None:
    async def scenario() -> None:
        socket = FakeSocket()
        await manager("COMPLETED").handle(socket, 1, object())
        assert socket.closed == (1008, "interview session is not in progress")

    asyncio.run(scenario())


def test_close_all_only_closes_registered_runtime_once() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.calls = 0

        async def close(self, **_kwargs) -> None:
            self.calls += 1

    async def scenario() -> None:
        instance = manager()
        runtime = Runtime()
        instance._runtimes[7] = runtime
        await instance.close_all()
        assert runtime.calls == 1
        assert instance.active_session_ids() == ()

    asyncio.run(scenario())

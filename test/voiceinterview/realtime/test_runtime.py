import asyncio
import base64
from types import SimpleNamespace

from starlette.websockets import WebSocketState

from modules.voiceinterview.realtime.runtime import VoiceInterviewRuntime


class FakeWebSocket:
    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.sent: list[dict] = []
        self.closed: tuple[int, str] | None = None

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)
        self.application_state = WebSocketState.DISCONNECTED


class FakeAsrStream:
    def __init__(self) -> None:
        self.audio: list[bytes] = []
        self.closed = False

    async def send_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def close(self) -> None:
        self.closed = True


class FakeAsrProvider:
    def __init__(self) -> None:
        self.callbacks = None
        self.stream = FakeAsrStream()

    async def open(self, _session_id, callbacks):
        self.callbacks = callbacks
        return self.stream


class FakeTts:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        if text.startswith("第二"):
            await asyncio.sleep(0.001)
        return b"\x00\x00" * len(text)


class FakeConversation:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def generate_reply(self, _db, _session, user_text: str) -> str:
        self.inputs.append(user_text)
        return "第一问。第二问！"


class FakeSessions:
    def __init__(self) -> None:
        self.phase = None

    async def get_session(self, _db, _session_id):
        return SimpleNamespace(status="IN_PROGRESS", current_phase=self.phase)

    async def start_phase(self, _db, _session_id, phase):
        self.phase = phase
        return phase

    async def end_session(self, _db, _session_id):
        return SimpleNamespace(status="COMPLETED")


def make_runtime():
    websocket = FakeWebSocket()
    asr = FakeAsrProvider()
    tts = FakeTts()
    conversation = FakeConversation()
    sessions = FakeSessions()
    runtime = VoiceInterviewRuntime(
        websocket=websocket,
        session_id=1,
        db=object(),
        session=SimpleNamespace(status="IN_PROGRESS"),
        asr_provider=asr,
        tts_provider=tts,
        conversation_service=conversation,
        session_service=sessions,
        cooldown_ms=800,
    )
    runtime.asr = asr.stream
    return runtime, websocket, asr, tts, conversation


def test_asr_callbacks_send_partial_and_buffer_only_final_text() -> None:
    async def scenario() -> None:
        runtime, websocket, *_ = make_runtime()
        await runtime._on_partial("正在识别")
        await runtime._on_final("最终回答")
        assert runtime.final_transcripts == ["最终回答"]
        assert websocket.sent == [
            {"type": "subtitle", "text": "正在识别", "isFinal": False},
            {"type": "subtitle", "text": "最终回答", "isFinal": True},
        ]

    asyncio.run(scenario())


def test_submit_prefers_explicit_text_and_emits_ordered_wav_chunks() -> None:
    async def scenario() -> None:
        runtime, websocket, _asr, tts, conversation = make_runtime()
        runtime.final_transcripts.extend(["识别", "结果"])
        await runtime.handle_message({"type": "control", "action": "submit", "data": {"text": " 修正答案 "}})
        assert conversation.inputs == ["修正答案"]
        assert runtime.final_transcripts == []
        assert tts.calls == ["第一问。", "第二问！"]
        text = next(item for item in websocket.sent if item["type"] == "text")
        assert text == {"type": "text", "content": "第一问。第二问！", "final": True}
        chunks = [item for item in websocket.sent if item["type"] == "audio_chunk"]
        assert [item["index"] for item in chunks] == [0, 1]
        assert [item["isLast"] for item in chunks] == [False, True]
        assert all(base64.b64decode(item["data"]).startswith(b"RIFF") for item in chunks)
        assert websocket.sent[-1]["action"] == "audio_complete"

    asyncio.run(scenario())


def test_audio_is_validated_and_ignored_during_ai_playback() -> None:
    async def scenario() -> None:
        runtime, websocket, asr, *_ = make_runtime()
        await runtime.handle_message({"type": "audio", "data": "not base64"})
        assert websocket.sent[-1]["type"] == "error"
        runtime.ai_speaking = True
        await runtime.handle_message({"type": "audio", "data": base64.b64encode(b"\x00\x00").decode()})
        assert asr.stream.audio == []
        runtime.ai_speaking = False
        runtime.ignore_audio_until = 0
        await runtime.handle_message({"type": "audio", "data": base64.b64encode(b"\x00\x00").decode()})
        assert asr.stream.audio == [b"\x00\x00"]

    asyncio.run(scenario())


def test_start_phase_and_end_controls_delegate_to_session_service() -> None:
    async def scenario() -> None:
        runtime, websocket, *_ = make_runtime()
        await runtime.handle_message({"type": "control", "action": "start_phase", "phase": "TECHNICAL"})
        assert runtime.session.current_phase == "TECHNICAL"
        await runtime.handle_message({"type": "control", "action": "end_interview"})
        assert runtime.closed is True
        assert [item["action"] for item in websocket.sent] == ["phase_started", "interview_ended"]

    asyncio.run(scenario())

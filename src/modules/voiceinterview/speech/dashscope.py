from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .protocols import AsrCallbacks, AsrProvider, AsrStream, TtsProvider


class SpeechConfigurationError(RuntimeError):
    pass


class DashScopeSpeechError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DashScopeAsrConfig:
    api_key: str | None = None
    url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    model: str = "qwen3-asr-flash-realtime"
    language: str = "zh"
    format: str = "pcm"
    sample_rate: int = 16000
    enable_turn_detection: bool = True
    turn_detection_type: str = "server_vad"
    turn_detection_threshold: float = 0.0
    turn_detection_silence_duration_ms: int = 1000
    connect_timeout_seconds: float = 10.0
    receive_timeout_seconds: float = 45.0


@dataclass(frozen=True, slots=True)
class DashScopeTtsConfig:
    api_key: str | None = None
    url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    model: str = "qwen-tts-realtime"
    voice: str = "Cherry"
    format: str = "pcm"
    sample_rate: int = 24000
    mode: str = "commit"
    language_type: str = "Chinese"
    speech_rate: float = 1.0
    volume: int = 60
    connect_timeout_seconds: float = 10.0
    response_timeout_seconds: float = 30.0


def _headers(api_key: str | None) -> dict[str, str]:
    if not api_key or not api_key.strip():
        raise SpeechConfigurationError("DashScope API key is not configured")
    return {"Authorization": f"Bearer {api_key.strip()}"}


def _event_type(payload: dict[str, Any]) -> str:
    return str(payload.get("type") or payload.get("event") or "")


def _new_event_id() -> str:
    return f"event_{uuid.uuid4().hex}"


def _asr_session_update(config: DashScopeAsrConfig) -> dict[str, Any]:
    return {
        "event_id": _new_event_id(),
        "type": "session.update",
        "session": {
            "modalities": ["text"],
            "input_audio_format": config.format,
            "sample_rate": config.sample_rate,
            "input_audio_transcription": {"language": config.language},
            "turn_detection": (
                {
                    "type": config.turn_detection_type,
                    "threshold": config.turn_detection_threshold,
                    "silence_duration_ms": config.turn_detection_silence_duration_ms,
                }
                if config.enable_turn_detection
                else None
            ),
        },
    }


def _tts_session_update(config: DashScopeTtsConfig) -> dict[str, Any]:
    return {
        "event_id": _new_event_id(),
        "type": "session.update",
        "session": {
            "voice": config.voice,
            "response_format": config.format,
            "sample_rate": config.sample_rate,
            "mode": config.mode,
            "language_type": config.language_type,
            "speech_rate": config.speech_rate,
            "volume": config.volume,
        },
    }


def _event_text(payload: dict[str, Any]) -> str:
    transcript = payload.get("transcript")
    if isinstance(transcript, str):
        return transcript
    text = payload.get("text") or payload.get("delta")
    if isinstance(text, str):
        return text
    item = payload.get("item")
    if isinstance(item, dict):
        value = item.get("transcript") or item.get("text")
        return value if isinstance(value, str) else ""
    return ""


class _DashScopeAsrStream(AsrStream):
    def __init__(
        self,
        http: aiohttp.ClientSession,
        websocket: aiohttp.ClientWebSocketResponse,
        callbacks: AsrCallbacks,
        receive_timeout: float,
    ) -> None:
        self._http = http
        self._websocket = websocket
        self._callbacks = callbacks
        self._receive_timeout = receive_timeout
        self._closed = False
        self._finished = asyncio.Event()
        self._reader = asyncio.create_task(self._read_events(), name="dashscope-asr-reader")

    async def send_audio(self, pcm: bytes) -> None:
        if self._closed:
            raise DashScopeSpeechError("ASR stream is closed")
        await self._websocket.send_json(
            {
                "event_id": _new_event_id(),
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm).decode("ascii"),
            }
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            await self._websocket.send_json({"event_id": _new_event_id(), "type": "session.finish"})
        current = asyncio.current_task()
        if self._reader is not current:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._finished.wait(), timeout=2.0)
            if not self._reader.done():
                self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        await self._websocket.close()
        await self._http.close()

    async def _read_events(self) -> None:
        try:
            while not self._closed:
                try:
                    message = await asyncio.wait_for(self._websocket.receive(), self._receive_timeout)
                except asyncio.TimeoutError:
                    # Silence is normal in an interview. Probe the transport
                    # instead of treating a quiet candidate as an ASR failure.
                    await self._websocket.ping()
                    continue
                if message.type == aiohttp.WSMsgType.TEXT:
                    payload = json.loads(message.data)
                    event = _event_type(payload)
                    if event in {"session.created", "session.updated"}:
                        await self._callbacks.on_ready()
                    elif event in {
                        "conversation.item.input_audio_transcription.delta",
                        "conversation.item.input_audio_transcription.text",
                    }:
                        text = _event_text(payload)
                        if text:
                            await self._callbacks.on_partial(text)
                    elif event in {
                        "conversation.item.input_audio_transcription.completed",
                        "input_audio_buffer.committed",
                    }:
                        text = _event_text(payload)
                        if text:
                            await self._callbacks.on_final(text)
                    elif event == "error":
                        raise DashScopeSpeechError(str(payload.get("error") or payload))
                    elif event == "session.finished":
                        self._finished.set()
                        break
                elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                    raise DashScopeSpeechError("DashScope ASR connection closed")
                elif message.type == aiohttp.WSMsgType.ERROR:
                    raise DashScopeSpeechError(str(self._websocket.exception()))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closed:
                await self._callbacks.on_error(exc if isinstance(exc, Exception) else Exception(str(exc)))


class DashScopeAsrProvider(AsrProvider):
    def __init__(self, config: DashScopeAsrConfig) -> None:
        self.config = config

    async def open(self, session_id: str, callbacks: AsrCallbacks) -> AsrStream:
        del session_id  # provider connection is already isolated per interview runtime
        headers = _headers(self.config.api_key)
        timeout = aiohttp.ClientTimeout(total=None, connect=self.config.connect_timeout_seconds)
        http = aiohttp.ClientSession(timeout=timeout)
        try:
            url = f"{self.config.url}?{urlencode({'model': self.config.model})}"
            ws = await http.ws_connect(url, headers=headers, heartbeat=20)
            await ws.send_json(_asr_session_update(self.config))
            return _DashScopeAsrStream(http, ws, callbacks, self.config.receive_timeout_seconds)
        except Exception:
            await http.close()
            raise


class DashScopeTtsProvider(TtsProvider):
    def __init__(self, config: DashScopeTtsConfig) -> None:
        self.config = config

    async def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""
        headers = _headers(self.config.api_key)
        timeout = aiohttp.ClientTimeout(total=self.config.response_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            url = f"{self.config.url}?{urlencode({'model': self.config.model})}"
            async with http.ws_connect(url, headers=headers, heartbeat=20) as ws:
                await ws.send_json(_tts_session_update(self.config))
                await ws.send_json(
                    {"event_id": _new_event_id(), "type": "input_text_buffer.append", "text": text}
                )
                await ws.send_json({"event_id": _new_event_id(), "type": "input_text_buffer.commit"})
                audio = bytearray()
                finish_sent = False
                while True:
                    message = await ws.receive()
                    if message.type != aiohttp.WSMsgType.TEXT:
                        if message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                            break
                        if message.type == aiohttp.WSMsgType.ERROR:
                            raise DashScopeSpeechError(str(ws.exception()))
                        continue
                    payload = json.loads(message.data)
                    event = _event_type(payload)
                    if event in {"response.audio.delta", "audio.delta"}:
                        chunk = payload.get("delta") or payload.get("audio")
                        if isinstance(chunk, str):
                            audio.extend(base64.b64decode(chunk, validate=True))
                    elif event in {"response.audio.done", "response.done"} and not finish_sent:
                        await ws.send_json({"event_id": _new_event_id(), "type": "session.finish"})
                        finish_sent = True
                    elif event == "session.finished":
                        return bytes(audio)
                    elif event == "error":
                        raise DashScopeSpeechError(str(payload.get("error") or payload))
                if not audio:
                    raise DashScopeSpeechError("DashScope TTS returned no audio")
                return bytes(audio)

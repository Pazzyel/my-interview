from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import logging
import time
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from modules.voiceinterview.speech.audio import InvalidAudioError, pcm_to_wav, split_sentences, validate_pcm16
from modules.voiceinterview.speech.protocols import AsrCallbacks, AsrProvider, AsrStream, TtsProvider

from .protocols import ConversationServiceProtocol, SessionServiceProtocol

logger = logging.getLogger(__name__)


class VoiceInterviewRuntime:
    """All mutable realtime state for exactly one WebSocket connection."""

    def __init__(
        self,
        *,
        websocket: WebSocket,
        session_id: int,
        db: Any,
        session: Any,
        asr_provider: AsrProvider,
        tts_provider: TtsProvider,
        conversation_service: ConversationServiceProtocol,
        session_service: SessionServiceProtocol,
        cooldown_ms: int = 800,
        tts_concurrency: int = 3,
        max_asr_reconnects: int = 2,
    ) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.db = db
        self.session = session
        self.asr_provider = asr_provider
        self.tts_provider = tts_provider
        self.conversation_service = conversation_service
        self.session_service = session_service
        self.cooldown_seconds = cooldown_ms / 1000
        self.tts_concurrency = max(1, tts_concurrency)
        self.max_asr_reconnects = max(0, max_asr_reconnects)
        self.asr: AsrStream | None = None
        self.final_transcripts: list[str] = []
        self.ai_speaking = False
        self.ignore_audio_until = 0.0
        self.closed = False
        self._send_lock = asyncio.Lock()
        self._submit_lock = asyncio.Lock()
        self._asr_lock = asyncio.Lock()
        self._reconnect_attempts = 0
        self._background: set[asyncio.Task[Any]] = set()
        self._owner_task: asyncio.Task[Any] | None = None
        self._reconnect_task: asyncio.Task[Any] | None = None

    async def run(self) -> None:
        self._owner_task = asyncio.current_task()
        await self.websocket.accept()
        try:
            await self._open_asr()
            await self.send_control("welcome", "连接成功，准备开始语音面试")
            await self._send_opening_if_available()
            while not self.closed:
                payload = await self.websocket.receive_json()
                await self.handle_message(payload)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.exception("Voice runtime failed for session %s", self.session_id)
            await self.send_error(str(exc) or "语音面试连接初始化失败")
        finally:
            await self.close()

    async def _open_asr(self) -> None:
        async with self._asr_lock:
            if self.closed:
                return
            callbacks = AsrCallbacks(
                on_partial=self._on_partial,
                on_final=self._on_final,
                on_ready=self._on_ready,
                on_error=self._on_asr_error,
            )
            self.asr = await self.asr_provider.open(str(self.session_id), callbacks)

    async def _on_partial(self, text: str) -> None:
        await self.send({"type": "subtitle", "text": text, "isFinal": False})

    async def _on_final(self, text: str) -> None:
        text = text.strip()
        if text:
            self.final_transcripts.append(text)
            await self.send({"type": "subtitle", "text": text, "isFinal": True})

    async def _on_ready(self) -> None:
        self._reconnect_attempts = 0
        await self.send_control("asr_ready", "语音识别已就绪")

    async def _on_asr_error(self, exc: Exception) -> None:
        logger.warning("ASR failed for voice session %s: %s", self.session_id, exc)
        if self.closed:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        if self._reconnect_attempts >= self.max_asr_reconnects:
            await self.send_error("语音识别连接失败，请重新连接后重试")
            return
        self._reconnect_attempts += 1
        await self.send_control("asr_reconnecting", f"语音识别正在重连（{self._reconnect_attempts}）")
        self._reconnect_task = asyncio.create_task(
            self._reconnect_asr(), name=f"voice-asr-reconnect-{self.session_id}"
        )
        self._track(self._reconnect_task)

    async def _reconnect_asr(self) -> None:
        try:
            await asyncio.sleep(0.2)
            previous = self.asr
            self.asr = None
            if previous is not None:
                with contextlib.suppress(Exception):
                    await previous.close()
            try:
                await self._open_asr()
            except Exception as exc:
                self._reconnect_task = None
                await self._on_asr_error(exc)
        finally:
            if self._reconnect_task is asyncio.current_task():
                self._reconnect_task = None

    async def _send_opening_if_available(self) -> None:
        generate = getattr(self.conversation_service, "generate_opening", None)
        if not callable(generate):
            return
        try:
            opening = (await generate(self.db, self.session)).strip()
            if opening:
                await self.emit_reply(opening)
                self.ignore_audio_until = time.monotonic() + self.cooldown_seconds
        except Exception as exc:
            logger.exception("Opening question failed for voice session %s", self.session_id)
            with contextlib.suppress(Exception):
                await self.db.rollback()
            await self.send_error(f"开场问题生成失败：{exc}")
        finally:
            self.ai_speaking = False

    async def handle_message(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            await self.send_error("WebSocket 消息必须是 JSON 对象")
            return
        message_type = payload.get("type")
        if message_type == "audio":
            await self._handle_audio(payload.get("data"))
        elif message_type == "control":
            await self._handle_control(payload)
        else:
            await self.send_error(f"不支持的消息类型：{message_type}")

    async def _handle_audio(self, encoded: Any) -> None:
        if self.ai_speaking or time.monotonic() < self.ignore_audio_until:
            return
        if not isinstance(encoded, str):
            await self.send_error("audio.data 必须是 Base64 字符串")
            return
        try:
            pcm = validate_pcm16(base64.b64decode(encoded, validate=True))
        except (binascii.Error, InvalidAudioError, ValueError) as exc:
            await self.send_error(f"无效的 PCM 音频：{exc}")
            return
        if self.asr is None:
            await self.send_error("语音识别尚未就绪")
            return
        try:
            await self.asr.send_audio(pcm)
        except Exception as exc:
            await self._on_asr_error(exc)

    async def _handle_control(self, payload: dict[str, Any]) -> None:
        action = payload.get("action")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if action == "submit":
            explicit = data.get("text")
            text = explicit.strip() if isinstance(explicit, str) and explicit.strip() else " ".join(self.final_transcripts).strip()
            self.final_transcripts.clear()
            if not text:
                await self.send_error("没有可提交的回答")
                return
            await self._submit(text)
        elif action == "start_phase":
            phase = payload.get("phase") or data.get("phase")
            if not isinstance(phase, str) or not phase.strip():
                await self.send_error("start_phase 需要 phase")
                return
            await self.session_service.start_phase(self.db, self.session_id, phase.strip())
            # Implementations commonly return only the phase enum. Reload the
            # complete entity so subsequent prompt generation retains skill/JD.
            self.session = await self.session_service.get_session(self.db, self.session_id)
            await self.send_control("phase_started", f"已进入 {phase.strip()} 阶段")
        elif action == "end_interview":
            await self.session_service.end_session(self.db, self.session_id)
            await self.send_control("interview_ended", "面试已结束")
            await self.close(code=1000, reason="interview ended")
            await self.close(code=1000, reason="interview ended")
        else:
            await self.send_error(f"不支持的控制操作：{action}")

    async def _submit(self, user_text: str) -> None:
        if self._submit_lock.locked():
            await self.send_error("上一条回答仍在处理中")
            return
        async with self._submit_lock:
            self.session = await self.session_service.get_session(self.db, self.session_id)
            status = getattr(self.session, "status", None)
            if getattr(status, "value", status) != "IN_PROGRESS":
                await self.send_error("当前会话不处于进行中状态")
                return
            self.ai_speaking = True
            try:
                reply = (await self.conversation_service.generate_reply(
                    self.db, self.session, user_text
                )).strip()
                if not reply:
                    raise RuntimeError("LLM returned an empty question")
                await self.emit_reply(reply)
            except Exception as exc:
                logger.exception("Voice reply generation failed for session %s", self.session_id)
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                await self.send_error(f"问题生成失败：{exc}")
            finally:
                self.ai_speaking = False
                self.ignore_audio_until = time.monotonic() + self.cooldown_seconds

    async def emit_reply(self, reply: str) -> None:
        """Send persisted LLM text first, then ordered TTS chunks."""
        self.ai_speaking = True
        await self.send({"type": "text", "content": reply, "final": True})
        sentences = split_sentences(reply)
        semaphore = asyncio.Semaphore(self.tts_concurrency)

        async def synthesize(sentence: str) -> bytes:
            async with semaphore:
                pcm = await self.tts_provider.synthesize(sentence)
                return pcm_to_wav(pcm) if pcm else b""

        results = await asyncio.gather(*(synthesize(sentence) for sentence in sentences), return_exceptions=True)
        successful = [result for result in results if isinstance(result, bytes) and result]
        for index, wav in enumerate(successful):
            await self.send(
                {
                    "type": "audio_chunk",
                    "data": base64.b64encode(wav).decode("ascii"),
                    "index": index,
                    "isLast": index == len(successful) - 1,
                }
            )
        failures = sum(isinstance(result, Exception) for result in results)
        if failures:
            logger.warning("TTS partially failed for session %s: %s sentence(s)", self.session_id, failures)
        await self.send_control("audio_complete", "面试官语音播放完成")

    async def send(self, payload: dict[str, Any]) -> None:
        if self.closed or self.websocket.application_state != WebSocketState.CONNECTED:
            return
        async with self._send_lock:
            await self.websocket.send_json(payload)

    async def send_control(self, action: str, message: str) -> None:
        await self.send(
            {"type": "control", "action": action, "message": message, "timestamp": int(time.time() * 1000)}
        )

    async def send_error(self, message: str) -> None:
        await self.send({"type": "error", "message": message})

    def _track(self, task: asyncio.Task[Any]) -> None:
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def close(self, *, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        self.closed = True
        owner = self._owner_task
        current = asyncio.current_task()
        if owner is not None and owner is not current and not owner.done():
            owner.cancel()
        for task in list(self._background):
            task.cancel()
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)
        if self.asr is not None:
            with contextlib.suppress(Exception):
                await self.asr.close()
            self.asr = None
        if self.websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await self.websocket.close(code=code, reason=reason)

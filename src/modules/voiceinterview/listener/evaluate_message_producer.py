import asyncio
from dataclasses import dataclass
from typing import Any

from common.async_task.abstract_message_producer import AbstractMessageProducer
from common.config import app_config


@dataclass(frozen=True)
class VoiceEvaluatePayload:
    session_id: int
    retry_count: int = 0


class VoiceEvaluateMessageProducer(AbstractMessageProducer[VoiceEvaluatePayload]):
    def send_evaluate_task(self, session_id: int, retry_count: int = 0) -> None:
        self.send_task(VoiceEvaluatePayload(session_id, retry_count))

    async def send_evaluate_task_async(self, session_id: int, retry_count: int = 0) -> None:
        await asyncio.to_thread(self.send_evaluate_task, session_id, retry_count)

    def task_display_name(self) -> str:
        return "语音面试评估"

    def topic(self) -> str:
        return app_config.voice_interview_evaluate_topic

    def tag(self) -> str:
        return app_config.voice_interview_evaluate_tag

    def build_message(self, payload: VoiceEvaluatePayload) -> dict[str, Any]:
        return {"sessionId": payload.session_id, "retryCount": payload.retry_count}

    def payload_identifier(self, payload: VoiceEvaluatePayload) -> str:
        return f"sessionId={payload.session_id}"

    def on_send_failed(self, payload: VoiceEvaluatePayload, error: str) -> None:
        # The session remains PENDING and is recovered by the database scanner.
        del payload, error

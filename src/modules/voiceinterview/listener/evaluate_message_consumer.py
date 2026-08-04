from dataclasses import dataclass
from typing import Any, Coroutine

from common.async_task.abstract_stream_consumer import AbstractStreamConsumer
from common.config import app_config
from modules.voiceinterview.listener.evaluate_message_producer import VoiceEvaluateMessageProducer
from modules.voiceinterview.service.evaluation_service import VoiceInterviewEvaluationService


@dataclass(frozen=True)
class VoiceEvaluateMessage:
    session_id: int
    retry_count: int = 0


class VoiceEvaluateMessageConsumer(AbstractStreamConsumer[VoiceEvaluateMessage]):
    def __init__(self, service: VoiceInterviewEvaluationService, producer: VoiceEvaluateMessageProducer):
        super().__init__()
        self._service = service
        self._producer = producer

    def consumer_display_name(self) -> str:
        return "Voice interview evaluate"

    def consumer_group(self) -> str:
        return app_config.voice_interview_evaluate_consumer_group

    def topic(self) -> str:
        return app_config.voice_interview_evaluate_topic

    def tag(self) -> str:
        return app_config.voice_interview_evaluate_tag

    def parse_payload(self, payload_dict: Any) -> VoiceEvaluateMessage | None:
        try:
            session_id = int(payload_dict.get("sessionId"))
            retry_count = int(payload_dict.get("retryCount", 0))
        except (TypeError, ValueError, AttributeError):
            return None
        return VoiceEvaluateMessage(session_id, retry_count) if session_id > 0 else None

    def process_payload(self, payload: VoiceEvaluateMessage) -> Coroutine[Any, Any, None]:
        return self._service.process(payload.session_id)

    def requeue_payload(self, payload: VoiceEvaluateMessage, retry_count: int) -> None:
        self._producer.send_evaluate_task(payload.session_id, retry_count)

    def mark_failed(self, payload: VoiceEvaluateMessage, error_message: str) -> Coroutine[Any, Any, None]:
        return self._service.mark_failed(payload.session_id, error_message)

    def payload_retry_count(self, payload: VoiceEvaluateMessage) -> int:
        return payload.retry_count

    def payload_identifier(self, payload: VoiceEvaluateMessage) -> str:
        return f"sessionId={payload.session_id}"

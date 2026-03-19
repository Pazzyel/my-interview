from dataclasses import dataclass
import logging
from typing import Any, Coroutine, Optional

from common.async_task.abstract_stream_consumer import AbstractStreamConsumer
from common.config import app_config
from modules.interview.listener.evaluate_message_producer import EvaluateMessageProducer
from modules.interview.service.interview_evaluate_consumer_service import InterviewEvaluateConsumerService

logger = logging.getLogger(__name__)


@dataclass
class EvaluateMessagePayload:
    """面试评估消息载荷。"""

    session_id: str
    retry_count: int


class EvaluateMessageConsumer(AbstractStreamConsumer[EvaluateMessagePayload]):
    """
    面试评估 RocketMQ 消费者。

    RocketMQ consumer for interview evaluation tasks.
    """

    def __init__(
        self,
        interview_evaluate_consumer_service: InterviewEvaluateConsumerService,
        evaluate_message_producer: EvaluateMessageProducer,
    ) -> None:
        super().__init__()
        self._interview_evaluate_consumer_service: InterviewEvaluateConsumerService = interview_evaluate_consumer_service
        self._evaluate_message_producer: EvaluateMessageProducer = evaluate_message_producer
    def consumer_display_name(self) -> str:
        return "Interview evaluate"

    def consumer_group(self) -> str:
        return app_config.interview_evaluate_consumer_group

    def topic(self) -> str:
        return app_config.interview_evaluate_topic

    def tag(self) -> str:
        return app_config.interview_evaluate_tag

    def parse_payload(self, payload_dict: Any) -> Optional[EvaluateMessagePayload]:
        session_id_value: Any = payload_dict.get("sessionId")
        retry_count_value: Any = payload_dict.get("retryCount", 0)

        try:
            session_id: str = str(session_id_value)
            retry_count: int = int(retry_count_value)
        except Exception:
            logger.warning("Interview evaluate message missing required fields: %s", payload_dict)
            return None

        if session_id.strip() == "":
            logger.warning("Interview evaluate message empty sessionId, skip")
            return None

        return EvaluateMessagePayload(session_id=session_id, retry_count=retry_count)

    def process_payload(self, payload: EvaluateMessagePayload) -> Coroutine[Any, Any, None]:
        return self._interview_evaluate_consumer_service.process_task(payload.session_id)

    def requeue_payload(self, payload: EvaluateMessagePayload, retry_count: int) -> None:
        self._evaluate_message_producer.send_evaluate_task(payload.session_id, retry_count)

    def mark_failed(self, payload: EvaluateMessagePayload, error_message: str) -> Coroutine[Any, Any, None]:
        return self._interview_evaluate_consumer_service.mark_failed(payload.session_id, error_message)

    def payload_retry_count(self, payload: EvaluateMessagePayload) -> int:
        return payload.retry_count

    def payload_identifier(self, payload: EvaluateMessagePayload) -> str:
        return f"sessionId={payload.session_id}"

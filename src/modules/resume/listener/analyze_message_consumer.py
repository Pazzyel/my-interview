from dataclasses import dataclass
import logging
from typing import Any, Coroutine, Optional

from common.async_task.abstract_stream_consumer import AbstractStreamConsumer
from common.config import app_config
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.service.resume_analyze_consumer_service import ResumeAnalyzeConsumerService

logger = logging.getLogger(__name__)


@dataclass
class AnalyzeMessagePayload:
    """简历分析消息载荷。"""

    resume_id: int
    content: str
    retry_count: int


class AnalyzeMessageConsumer(AbstractStreamConsumer[AnalyzeMessagePayload]):
    """Resume analyze RocketMQ consumer."""

    def __init__(
        self,
        resume_analyze_consumer_service: ResumeAnalyzeConsumerService,
        analyze_message_producer: AnalyzeMessageProducer,
    ) -> None:
        super().__init__()
        self._resume_analyze_consumer_service: ResumeAnalyzeConsumerService = resume_analyze_consumer_service
        self._analyze_message_producer: AnalyzeMessageProducer = analyze_message_producer

    def consumer_display_name(self) -> str:
        return "Resume analyze"

    def consumer_group(self) -> str:
        return app_config.rocketmq_consumer_group

    def topic(self) -> str:
        return app_config.resume_analyze_topic

    def tag(self) -> str:
        return app_config.resume_analyze_tag

    def parse_payload(self, payload_dict: Any) -> Optional[AnalyzeMessagePayload]:
        resume_id_value: Any = payload_dict.get("resumeId")
        content_value: Any = payload_dict.get("content")
        retry_count_value: Any = payload_dict.get("retryCount", 0)

        try:
            resume_id: int = int(resume_id_value)
            content: str = str(content_value)
            retry_count: int = int(retry_count_value)
        except Exception:
            logger.warning("Analyze message missing required fields: %s", payload_dict)
            return None

        if content.strip() == "":
            logger.warning("Analyze message empty content, skip: resumeId=%s", resume_id)
            return None

        return AnalyzeMessagePayload(resume_id=resume_id, content=content, retry_count=retry_count)

    def process_payload(self, payload: AnalyzeMessagePayload) -> Coroutine[Any, Any, None]:
        return self._resume_analyze_consumer_service.process_task(payload.resume_id, payload.content)

    def requeue_payload(self, payload: AnalyzeMessagePayload, retry_count: int) -> None:
        self._analyze_message_producer.send_analyze_task(payload.resume_id, payload.content, retry_count)

    def mark_failed(self, payload: AnalyzeMessagePayload, error_message: str) -> Coroutine[Any, Any, None]:
        return self._resume_analyze_consumer_service.mark_failed(payload.resume_id, error_message)

    def payload_retry_count(self, payload: AnalyzeMessagePayload) -> int:
        return payload.retry_count

    def payload_identifier(self, payload: AnalyzeMessagePayload) -> str:
        return f"resumeId={payload.resume_id}"

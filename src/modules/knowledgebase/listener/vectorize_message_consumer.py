from dataclasses import dataclass
import logging
from typing import Any, Coroutine, Optional

from common.async_task.abstract_stream_consumer import AbstractStreamConsumer
from common.config import app_config
from modules.knowledgebase.listener.vectorize_message_producer import VectorizeMessageProducer
from modules.knowledgebase.service.knowledgebase_vectorize_consumer_service import \
    KnowledgeBaseVectorizeConsumerService

logger = logging.getLogger(__name__)


@dataclass
class VectorizeMessagePayload:
    """知识库向量化消息载荷。"""

    kb_id: int
    kb_name: Optional[str]
    kb_category: Optional[str]
    content: str
    retry_count: int


class VectorizeMessageConsumer(AbstractStreamConsumer[VectorizeMessagePayload]):
    """Knowledgebase vectorize RocketMQ consumer."""

    def __init__(
        self,
        knowledgebase_vectorize_consumer_service: KnowledgeBaseVectorizeConsumerService,
        vectorize_message_producer: VectorizeMessageProducer,
    ) -> None:
        super().__init__()
        self._knowledgebase_vectorize_consumer_service: KnowledgeBaseVectorizeConsumerService = (
            knowledgebase_vectorize_consumer_service
        )
        self._vectorize_message_producer: VectorizeMessageProducer = vectorize_message_producer

    def consumer_display_name(self) -> str:
        return "Knowledgebase vectorize"

    def consumer_group(self) -> str:
        return app_config.kb_vectorize_consumer_group

    def topic(self) -> str:
        return app_config.kb_vectorize_topic

    def tag(self) -> str:
        return app_config.kb_vectorize_tag

    def parse_payload(self, payload_dict: Any) -> Optional[VectorizeMessagePayload]:
        kb_id_value: Any = payload_dict.get("kbId")
        kb_name_value: Any = payload_dict.get("kbName")
        kb_category_value: Any = payload_dict.get("kbCategory")
        content_value: Any = payload_dict.get("content")
        retry_count_value: Any = payload_dict.get("retryCount", 0)

        try:
            kb_id: int = int(kb_id_value)
            kb_name: Optional[str] = str(kb_name_value) if kb_name_value is not None else None
            kb_category: Optional[str] = str(kb_category_value) if kb_category_value is not None else None
            content: str = str(content_value)
            retry_count: int = int(retry_count_value)
        except Exception:
            logger.warning("Knowledgebase vectorize message missing required fields: %s", payload_dict)
            return None

        if content.strip() == "":
            logger.warning("Knowledgebase vectorize message empty content, skip: kbId=%s", kb_id)
            return None

        return VectorizeMessagePayload(
            kb_id=kb_id,
            kb_name=kb_name,
            kb_category=kb_category,
            content=content,
            retry_count=retry_count,
        )

    def process_payload(self, payload: VectorizeMessagePayload) -> Coroutine[Any, Any, None]:
        return self._knowledgebase_vectorize_consumer_service.process_task(
            kb_id=payload.kb_id,
            content=payload.content,
            kb_name=payload.kb_name,
            kb_category=payload.kb_category,
        )

    def requeue_payload(self, payload: VectorizeMessagePayload, retry_count: int) -> None:
        self._vectorize_message_producer.send_vectorize_task(
            kb_id=payload.kb_id,
            kb_name=payload.kb_name or "",
            kb_category=payload.kb_category or "",
            content=payload.content,
            retry_count=retry_count,
        )

    def mark_failed(self, payload: VectorizeMessagePayload, error_message: str) -> Coroutine[Any, Any, None]:
        return self._knowledgebase_vectorize_consumer_service.mark_failed(payload.kb_id, error_message)

    def payload_retry_count(self, payload: VectorizeMessagePayload) -> int:
        return payload.retry_count

    def payload_identifier(self, payload: VectorizeMessagePayload) -> str:
        return f"kbId={payload.kb_id}"

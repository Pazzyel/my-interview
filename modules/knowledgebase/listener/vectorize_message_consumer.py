import asyncio
import json
import logging
from typing import Any, Dict, Optional

from rocketmq.client import ConsumeStatus, PushConsumer

from common.config import app_config
from modules.knowledgebase.listener.vectorize_message_producer import VectorizeMessageProducer
from modules.knowledgebase.service.knowledgebase_vectorize_consumer_service import KnowledgeBaseVectorizeConsumerService

logger = logging.getLogger(__name__)


class VectorizeMessageConsumer:
    """Knowledgebase vectorize RocketMQ consumer."""

    def __init__(
        self,
        knowledgebase_vectorize_consumer_service: KnowledgeBaseVectorizeConsumerService,
        vectorize_message_producer: VectorizeMessageProducer,
    ) -> None:
        self._knowledgebase_vectorize_consumer_service: KnowledgeBaseVectorizeConsumerService = (
            knowledgebase_vectorize_consumer_service
        )
        self._vectorize_message_producer: VectorizeMessageProducer = vectorize_message_producer
        self._consumer: Optional[PushConsumer] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._started: bool = False

    async def start(self) -> None:
        """
        启动 RocketMQ 知识库向量化消费者并注册消息回调。

        Start RocketMQ consumer for knowledgebase vectorization and register callback.

        关键行为 / Key Behaviors:
        1) 记录主事件循环，供消费线程回调提交协程。
        2) 绑定 NameServer 与 Topic/Tag。
        3) 启动 PushConsumer 并记录状态。
        """
        if self._started:
            return

        self._main_loop = asyncio.get_running_loop()
        consumer: PushConsumer = PushConsumer(app_config.kb_vectorize_consumer_group)
        consumer.set_name_server_address(app_config.rocketmq_name_server)
        consumer.subscribe(app_config.kb_vectorize_topic, self._on_message, app_config.kb_vectorize_tag)
        consumer.start()

        self._consumer = consumer
        self._started = True
        logger.info(
            "Knowledgebase vectorize consumer started: topic=%s, tag=%s, group=%s",
            app_config.kb_vectorize_topic,
            app_config.kb_vectorize_tag,
            app_config.kb_vectorize_consumer_group,
        )

    async def shutdown(self) -> None:
        """Shutdown consumer safely."""
        if not self._started:
            return

        if self._consumer is not None:
            self._consumer.shutdown()

        self._consumer = None
        self._started = False
        logger.info("Knowledgebase vectorize consumer stopped")

    def _on_message(self, message: Any) -> ConsumeStatus:
        """RocketMQ callback. Parse message and dispatch to async service."""
        try:
            raw_body: bytes = message.body
            payload_dict: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
        except Exception as error:
            logger.error("Invalid knowledgebase vectorize message body: %s", str(error), exc_info=True)
            return ConsumeStatus.CONSUME_SUCCESS

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
            return ConsumeStatus.CONSUME_SUCCESS

        if content.strip() == "":
            logger.warning("Knowledgebase vectorize message empty content, skip: kbId=%s", kb_id)
            return ConsumeStatus.CONSUME_SUCCESS

        try:
            self._run_coroutine(
                self._knowledgebase_vectorize_consumer_service.process_task(
                    kb_id=kb_id,
                    content=content,
                    kb_name=kb_name,
                    kb_category=kb_category,
                )
            )
            return ConsumeStatus.CONSUME_SUCCESS
        except Exception as error:
            error_message: str = f"Knowledgebase vectorize failed: {str(error)}"
            logger.error("Knowledgebase vectorize task failed: kbId=%s, error=%s", kb_id, str(error), exc_info=True)

            if retry_count < app_config.rocketmq_max_retry_count:
                self._vectorize_message_producer.send_vectorize_task(
                    kb_id=kb_id,
                    kb_name=kb_name or "",
                    kb_category=kb_category or "",
                    content=content,
                    retry_count=retry_count + 1,
                )
                logger.info(
                    "Knowledgebase vectorize task requeued: kbId=%s, retryCount=%s",
                    kb_id,
                    retry_count + 1,
                )
                return ConsumeStatus.CONSUME_SUCCESS

            self._run_coroutine(self._knowledgebase_vectorize_consumer_service.mark_failed(kb_id, error_message))
            return ConsumeStatus.CONSUME_SUCCESS

    def _run_coroutine(self, coroutine: Any) -> Any:
        """Run coroutine on the main loop from RocketMQ callback thread."""
        if self._main_loop is None:
            raise RuntimeError("Consumer event loop not initialized")

        future = asyncio.run_coroutine_threadsafe(coroutine, self._main_loop)
        return future.result()

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from rocketmq.client import ConsumeStatus, PushConsumer

from common.config import app_config
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.service.resume_analyze_consumer_service import ResumeAnalyzeConsumerService

logger = logging.getLogger(__name__)


class AnalyzeMessageConsumer:
    """Resume analyze RocketMQ consumer."""

    def __init__(
        self,
        resume_analyze_consumer_service: ResumeAnalyzeConsumerService,
        analyze_message_producer: AnalyzeMessageProducer,
    ) -> None:
        self._resume_analyze_consumer_service: ResumeAnalyzeConsumerService = resume_analyze_consumer_service
        self._analyze_message_producer: AnalyzeMessageProducer = analyze_message_producer
        self._consumer: Optional[PushConsumer] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._started: bool = False

    async def start(self) -> None:
        """
        中文：启动 RocketMQ 简历分析消费者并注册消息回调。
        English: Start RocketMQ consumer for resume analysis and register callback.

        关键行为 / Key Behaviors:
        1) 记录主事件循环，供消费者线程回调提交协程。
        2) 绑定 NameServer 与 Topic/Tag。
        3) 启动 PushConsumer 并记录状态。
        """
        if self._started:
            return

        self._main_loop = asyncio.get_running_loop()
        consumer: PushConsumer = PushConsumer(app_config.rocketmq_consumer_group)
        consumer.set_name_server_address(app_config.rocketmq_name_server)
        consumer.subscribe(app_config.resume_analyze_topic, self._on_message, app_config.resume_analyze_tag)
        consumer.start()

        self._consumer = consumer
        self._started = True
        logger.info(
            "Resume analyze consumer started: topic=%s, tag=%s, group=%s",
            app_config.resume_analyze_topic,
            app_config.resume_analyze_tag,
            app_config.rocketmq_consumer_group,
        )

    async def shutdown(self) -> None:
        """Shutdown consumer safely."""
        if not self._started:
            return

        if self._consumer is not None:
            self._consumer.shutdown()

        self._consumer = None
        self._started = False
        logger.info("Resume analyze consumer stopped")

    def _on_message(self, message: Any) -> ConsumeStatus:
        """RocketMQ callback. Parse message and dispatch to async service."""
        try:
            raw_body: bytes = message.body
            payload_dict: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
        except Exception as error:
            logger.error("Invalid analyze message body: %s", str(error), exc_info=True)
            return ConsumeStatus.CONSUME_SUCCESS

        resume_id_value: Any = payload_dict.get("resumeId")
        content_value: Any = payload_dict.get("content")
        retry_count_value: Any = payload_dict.get("retryCount", 0)

        try:
            resume_id: int = int(resume_id_value)
            content: str = str(content_value)
            retry_count: int = int(retry_count_value)
        except Exception:
            logger.warning("Analyze message missing required fields: %s", payload_dict)
            return ConsumeStatus.CONSUME_SUCCESS

        if content.strip() == "":
            logger.warning("Analyze message empty content, skip: resumeId=%s", resume_id)
            return ConsumeStatus.CONSUME_SUCCESS

        try:
            self._run_coroutine(self._resume_analyze_consumer_service.process_task(resume_id, content))
            return ConsumeStatus.CONSUME_SUCCESS
        except Exception as error:
            error_message: str = f"Resume analyze failed: {str(error)}"
            logger.error("Resume analyze task failed: resumeId=%s, error=%s", resume_id, str(error), exc_info=True)

            if retry_count < app_config.rocketmq_max_retry_count:
                self._analyze_message_producer.send_analyze_task(resume_id, content, retry_count + 1)
                logger.info(
                    "Resume analyze task requeued: resumeId=%s, retryCount=%s",
                    resume_id,
                    retry_count + 1,
                )
                return ConsumeStatus.CONSUME_SUCCESS

            self._run_coroutine(self._resume_analyze_consumer_service.mark_failed(resume_id, error_message))
            return ConsumeStatus.CONSUME_SUCCESS

    def _run_coroutine(self, coroutine: Any) -> Any:
        """Run coroutine on the main loop from RocketMQ callback thread."""
        if self._main_loop is None:
            raise RuntimeError("Consumer event loop not initialized")

        future = asyncio.run_coroutine_threadsafe(coroutine, self._main_loop)
        return future.result()

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from rocketmq.client import ConsumeStatus, PushConsumer

from common.config import app_config
from modules.interview.listener.evaluate_message_producer import EvaluateMessageProducer
from modules.interview.service.interview_evaluate_consumer_service import InterviewEvaluateConsumerService

logger = logging.getLogger(__name__)


class EvaluateMessageConsumer:
    """
    面试评估 RocketMQ 消费者。

    RocketMQ consumer for interview evaluation tasks.
    """

    def __init__(
        self,
        interview_evaluate_consumer_service: InterviewEvaluateConsumerService,
        evaluate_message_producer: EvaluateMessageProducer,
    ) -> None:
        self._interview_evaluate_consumer_service: InterviewEvaluateConsumerService = interview_evaluate_consumer_service
        self._evaluate_message_producer: EvaluateMessageProducer = evaluate_message_producer
        self._consumer: Optional[PushConsumer] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._started: bool = False

    async def start(self) -> None:
        """
        启动面试评估消费者并注册消息回调

        Start interview evaluation consumer and register callback.
        """
        if self._started:
            return

        self._main_loop = asyncio.get_running_loop()
        consumer: PushConsumer = PushConsumer(app_config.interview_evaluate_consumer_group)
        consumer.set_name_server_address(app_config.rocketmq_name_server)
        consumer.subscribe(
            app_config.interview_evaluate_topic,
            self._on_message,
            app_config.interview_evaluate_tag,
        )
        consumer.start()

        self._consumer = consumer
        self._started = True
        logger.info(
            "Interview evaluate consumer started: topic=%s, tag=%s, group=%s",
            app_config.interview_evaluate_topic,
            app_config.interview_evaluate_tag,
            app_config.interview_evaluate_consumer_group,
        )

    async def shutdown(self) -> None:
        """关闭消费者。"""
        if not self._started:
            return

        if self._consumer is not None:
            self._consumer.shutdown()

        self._consumer = None
        self._started = False
        logger.info("Interview evaluate consumer stopped")

    def _on_message(self, message: Any) -> ConsumeStatus:
        """RocketMQ 回调，解析消息后转发到异步业务服务。"""
        try:
            raw_body: bytes = message.body
            payload_dict: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
        except Exception as error:
            logger.error("Invalid interview evaluate message body: %s", str(error), exc_info=True)
            return ConsumeStatus.CONSUME_SUCCESS

        session_id_value: Any = payload_dict.get("sessionId")
        retry_count_value: Any = payload_dict.get("retryCount", 0)

        try:
            session_id: str = str(session_id_value)
            retry_count: int = int(retry_count_value)
        except Exception:
            logger.warning("Interview evaluate message missing required fields: %s", payload_dict)
            return ConsumeStatus.CONSUME_SUCCESS

        if session_id.strip() == "":
            logger.warning("Interview evaluate message empty sessionId, skip")
            return ConsumeStatus.CONSUME_SUCCESS

        try:
            self._run_coroutine(self._interview_evaluate_consumer_service.process_task(session_id))
            return ConsumeStatus.CONSUME_SUCCESS
        except Exception as error:
            error_message: str = f"Interview evaluate failed: {str(error)}"
            logger.error("Interview evaluate task failed: sessionId=%s, error=%s", session_id, str(error), exc_info=True)

            if retry_count < app_config.rocketmq_max_retry_count:
                self._evaluate_message_producer.send_evaluate_task(session_id, retry_count + 1)
                logger.info(
                    "Interview evaluate task requeued: sessionId=%s, retryCount=%s",
                    session_id,
                    retry_count + 1,
                )
                return ConsumeStatus.CONSUME_SUCCESS

            self._run_coroutine(self._interview_evaluate_consumer_service.mark_failed(session_id, error_message))
            return ConsumeStatus.CONSUME_SUCCESS

    def _run_coroutine(self, coroutine: Any) -> Any:
        """在 RocketMQ 回调线程里将协程提交到主事件循环执行。"""
        if self._main_loop is None:
            raise RuntimeError("Consumer event loop not initialized")

        future = asyncio.run_coroutine_threadsafe(coroutine, self._main_loop)
        return future.result()

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Coroutine, Generic, Optional, TypeVar

from rocketmq import (
    ClientConfiguration,
    ConsumeResult,
    Credentials,
    FilterExpression,
    MessageListener,
    PushConsumer,
)

from common.config import app_config

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _CallbackMessageListener(MessageListener):
    def __init__(self, callback: Any):
        self._callback = callback

    def consume(self, message: Any) -> ConsumeResult:
        return self._callback(message)


class AbstractStreamConsumer(ABC, Generic[T]):
    """
    RocketMQ 流式消费者模板基类。
    统一封装消费端的启动、关闭、消息解析、重试与失败回写骨架流程。

    Abstract base class for RocketMQ stream consumers.
    It centralizes startup/shutdown lifecycle, message dispatch, retry handling,
    and failure marking workflow.
    """

    def __init__(self) -> None:
        self._consumer: Optional[PushConsumer] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._started: bool = False

    async def start(self) -> None:
        """
        启动消费者并注册回调。

        Start consumer and register callback.
        """
        if self._started:
            return

        self._main_loop = asyncio.get_running_loop()
        config = ClientConfiguration(app_config.rocketmq_endpoints, Credentials())
        listener = _CallbackMessageListener(self._on_message)
        subscription = {self.topic(): FilterExpression(self.tag() or "*")}
        consumer: PushConsumer = PushConsumer(
            client_configuration=config,
            consumer_group=self.consumer_group(),
            message_listener=listener,
            subscription=subscription,
        )
        consumer.startup()

        self._consumer = consumer
        self._started = True
        logger.info(
            "%s consumer started: topic=%s, tag=%s, group=%s",
            self.consumer_display_name(),
            self.topic(),
            self.tag(),
            self.consumer_group(),
        )

    async def shutdown(self) -> None:
        """安全关闭消费者 / Shutdown consumer safely."""
        if not self._started:
            return

        if self._consumer is not None:
            self._consumer.shutdown()

        self._consumer = None
        self._started = False
        logger.info("%s consumer stopped", self.consumer_display_name())

    def _on_message(self, message: Any) -> ConsumeResult:
        """
        RocketMQ 回调模板方法。

        RocketMQ callback template method.

        执行步骤 / Execution steps:
        1) 反序列化消息体并进行 payload 解析。
        2) 调用子类业务处理协程。
        3) 失败时按统一重试策略重新入队。
        4) 达到最大重试后执行失败落库。
        """
        try:
            raw_body: bytes = message.body
            payload_dict: Any = json.loads(raw_body.decode("utf-8"))
        except Exception as error:
            logger.error(
                "Invalid %s message body: %s",
                self.consumer_display_name(),
                str(error),
                exc_info=True,
            )
            return ConsumeResult.SUCCESS

        payload: Optional[T] = self.parse_payload(payload_dict)
        if payload is None:
            return ConsumeResult.SUCCESS

        try:
            self._run_coroutine(self.process_payload(payload))
            return ConsumeResult.SUCCESS
        except Exception as error:
            error_message: str = f"{self.consumer_display_name()} failed: {str(error)}"
            logger.error(
                "%s task failed: %s, error=%s",
                self.consumer_display_name(),
                self.payload_identifier(payload),
                str(error),
                exc_info=True,
            )

            current_retry_count: int = self.payload_retry_count(payload)
            if current_retry_count < app_config.rocketmq_max_retry_count:
                self.requeue_payload(payload, current_retry_count + 1)
                logger.info(
                    "%s task requeued: %s, retryCount=%s",
                    self.consumer_display_name(),
                    self.payload_identifier(payload),
                    current_retry_count + 1,
                )
                return ConsumeResult.SUCCESS

            self._run_coroutine(self.mark_failed(payload, error_message))
            return ConsumeResult.SUCCESS

    def _run_coroutine(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        """在回调线程中将协程提交至主事件循环执行 / Submit coroutine to main loop."""
        if self._main_loop is None:
            raise RuntimeError("Consumer event loop not initialized")

        future = asyncio.run_coroutine_threadsafe(coroutine, self._main_loop)
        return future.result()

    @abstractmethod
    def consumer_display_name(self) -> str:
        """日志展示名称 / Display name for logging."""
        ...

    @abstractmethod
    def consumer_group(self) -> str:
        """RocketMQ 消费组 / RocketMQ consumer group."""
        ...

    @abstractmethod
    def topic(self) -> str:
        """RocketMQ Topic。"""
        ...

    @abstractmethod
    def tag(self) -> str:
        """RocketMQ Tag。"""
        ...

    @abstractmethod
    def parse_payload(self, payload_dict: Any) -> Optional[T]:
        """解析并校验消息体 / Parse and validate message payload."""
        ...

    @abstractmethod
    def process_payload(self, payload: T) -> Coroutine[Any, Any, None]:
        """执行业务处理 / Execute business process coroutine."""
        ...

    @abstractmethod
    def requeue_payload(self, payload: T, retry_count: int) -> None:
        """重试入队 / Requeue payload with retry count."""
        ...

    @abstractmethod
    def mark_failed(self, payload: T, error_message: str) -> Coroutine[Any, Any, None]:
        """任务失败回写 / Mark task as failed."""
        ...

    @abstractmethod
    def payload_retry_count(self, payload: T) -> int:
        """读取当前重试次数 / Get current retry count from payload."""
        ...

    @abstractmethod
    def payload_identifier(self, payload: T) -> str:
        """读取载荷标识 / Get payload identifier for logging."""
        ...
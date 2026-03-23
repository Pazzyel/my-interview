import json
import logging
import threading
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Dict, Any, Optional, ClassVar, Coroutine

import asyncio

from rocketmq import ClientConfiguration, Credentials, Message, Producer

from common.config import app_config

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AbstractMessageProducer(ABC, Generic[T]):
    """
    RocketMQ 消息生产者模板基类。
    统一消息发送骨架与失败处理逻辑。
    """

    _producers: ClassVar[Dict[str, Producer]] = {}
    _producer_ref_counts: ClassVar[Dict[str, int]] = {}
    _producer_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._producer_group = self.producer_group()

        with self._producer_lock:
            producer = self._producers.get(self._producer_group)
            if producer is None:
                config = ClientConfiguration(app_config.rocketmq_endpoints, Credentials())
                producer = Producer(config, (self.topic(),))
                producer.startup()
                self._producers[self._producer_group] = producer
                self._producer_ref_counts[self._producer_group] = 0
                logger.info(
                    "RocketMQ Producer started: endpoints=%s, group=%s",
                    app_config.rocketmq_endpoints,
                    self._producer_group,
                )

            self._producer_ref_counts[self._producer_group] += 1
            self._producer = producer

    # ────────── 模板方法：发送任务 ──────────

    def send_task(self, payload: T) -> None:
        """
        发送任务消息到 RocketMQ（模板方法）。
        子类调用本方法，由基类完成序列化 → 发送 → 异常处理。
        """
        try:
            body = json.dumps(self.build_message(payload), ensure_ascii=False).encode("utf-8")

            msg = Message()
            msg.topic = self.topic()
            msg.keys = self.payload_identifier(payload)
            msg.tag = self.tag()
            msg.body = body

            send_result = self._producer.send(msg)

            logger.info(
                "%s 任务已发送到 RocketMQ: topic=%s, msg_id=%s, status=%s, %s",
                self.task_display_name(),
                self.topic(),
                send_result.message_id,
                "SUCCESS",
                self.payload_identifier(payload),
            )
        except Exception as e:
            logger.error(
                "发送 %s 任务失败: %s, error=%s",
                self.task_display_name(),
                self.payload_identifier(payload),
                str(e),
                exc_info=True,
            )
            self.on_send_failed(payload, f"任务入队失败: {e}")

    # ────────── 工具方法 ──────────

    @staticmethod
    def truncate_error(error: Optional[str], max_length: int = 500) -> Optional[str]:
        """截断过长的错误信息。"""
        if error is None:
            return None
        return error[:max_length] if len(error) > max_length else error

    def run_coroutine_safely(self, coroutine: Coroutine[Any, Any, None]) -> None:
        """
        在同步上下文中安全执行协程。

        - 若当前线程已有事件循环：使用 create_task 调度，避免 RuntimeError。
        - 若当前线程没有事件循环：使用 asyncio.run 同步执行。
        """
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coroutine)
            return

        task = running_loop.create_task(coroutine)

        def _log_task_exception(done_task: asyncio.Task[Any]) -> None:
            try:
                done_task.result()
            except Exception as exception:
                logger.error("异步失败回调执行异常: %s", str(exception), exc_info=True)

        task.add_done_callback(_log_task_exception)

    def shutdown(self) -> None:
        """关闭生产者，释放资源。"""
        with self._producer_lock:
            ref_count = self._producer_ref_counts.get(self._producer_group, 0)
            if ref_count <= 0:
                return

            ref_count -= 1
            self._producer_ref_counts[self._producer_group] = ref_count

            if ref_count == 0:
                producer = self._producers.pop(self._producer_group, None)
                self._producer_ref_counts.pop(self._producer_group, None)
                if producer is not None:
                    producer.shutdown()
                    logger.info("RocketMQ Producer closed: group=%s", self._producer_group)

    def producer_group(self) -> str:
        """RocketMQ Producer Group，子类可按需覆盖。"""
        return app_config.rocketmq_producer_group

    # ────────── 子类必须实现的抽象方法 ──────────

    @abstractmethod
    def task_display_name(self) -> str:
        """任务显示名称，用于日志。"""
        ...

    @abstractmethod
    def topic(self) -> str:
        """RocketMQ Topic。"""
        ...

    @abstractmethod
    def tag(self) -> str:
        """RocketMQ Tag，用于消费端过滤。"""
        ...

    @abstractmethod
    def build_message(self, payload: T) -> Dict[str, Any]:
        """将 payload 序列化为字典，最终会 JSON 序列化后作为消息体。"""
        ...

    @abstractmethod
    def payload_identifier(self, payload: T) -> str:
        """返回 payload 的唯一标识，用于日志和 Message Key。"""
        ...

    @abstractmethod
    def on_send_failed(self, payload: T, error: str) -> None:
        """发送失败时的回调（如更新数据库状态）。"""
        ...

import json
import logging
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Dict, Any, Optional

from rocketmq.client import Producer, Message

from common.config import app_config

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AbstractMessageProducer(ABC, Generic[T]):
    """
    RocketMQ 消息生产者模板基类。
    统一消息发送骨架与失败处理逻辑。
    """

    def __init__(self) -> None:
        self._producer = Producer(app_config.rocketmq_producer_group)
        self._producer.set_name_server_address(app_config.rocketmq_name_server)
        self._producer.start()
        logger.info(
            "RocketMQ Producer started: name_server=%s, group=%s",
            app_config.rocketmq_name_server,
            app_config.rocketmq_producer_group,
        )

    # ────────── 模板方法：发送任务 ──────────

    def send_task(self, payload: T) -> None:
        """
        发送任务消息到 RocketMQ（模板方法）。
        子类调用本方法，由基类完成序列化 → 发送 → 异常处理。
        """
        try:
            body = json.dumps(self.build_message(payload), ensure_ascii=False).encode("utf-8")

            msg = Message(self.topic())
            msg.set_keys(self.payload_identifier(payload))
            msg.set_tags(self.tag())
            msg.set_body(body)

            send_result = self._producer.send_sync(msg)

            logger.info(
                "%s 任务已发送到 RocketMQ: topic=%s, msg_id=%s, status=%s, %s",
                self.task_display_name(),
                self.topic(),
                send_result.msg_id,
                send_result.status,
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

    def shutdown(self) -> None:
        """关闭生产者，释放资源。"""
        self._producer.shutdown()
        logger.info("RocketMQ Producer closed.")

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

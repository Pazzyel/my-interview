from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from common.llm_provider import LlmProviderResolver
from common.prompt_security import sanitize_prompt_data, wrap_prompt_data

logger = logging.getLogger(__name__)


class ContextMode(str, Enum):
    NONE = "NONE"
    WINDOW = "WINDOW"
    SUMMARY = "SUMMARY"


class ContextMessageRepository(Protocol):
    async def list_for_context(self, db: AsyncSession, session_id: int) -> list[Any]: ...
    async def get_latest_summary(self, db: AsyncSession, session_id: int) -> Any | None: ...
    async def save_summary(
        self, db: AsyncSession, session_id: int, text: str, covered_sequence: int
    ) -> Any: ...


class VoiceInterviewContextService:
    def __init__(
        self,
        repository: ContextMessageRepository,
        resolver: LlmProviderResolver,
        mode: ContextMode | str = ContextMode.SUMMARY,
        window_size: int = 20,
        summary_batch_size: int = 10,
        summary_timeout_seconds: float = 20.0,
    ) -> None:
        self._repository = repository
        self._resolver = resolver
        self._mode = mode if isinstance(mode, ContextMode) else ContextMode(str(mode).upper())
        self._window_size = max(1, window_size)
        self._summary_batch_size = max(1, summary_batch_size)
        self._summary_timeout_seconds = summary_timeout_seconds

    async def build_context(
        self, db: AsyncSession, session_id: int, provider: str | None
    ) -> str:
        messages = await self._repository.list_for_context(db, session_id)
        if self._mode == ContextMode.NONE:
            return self._format(messages)
        if self._mode == ContextMode.WINDOW:
            return self._format(messages[-self._window_size :])

        summary = await self._repository.get_latest_summary(db, session_id)
        covered = int(self._value(summary, "summary_covered_sequence", 0) or 0)
        old_messages = [m for m in messages if int(self._value(m, "sequence_num", 0)) > covered]
        candidates = old_messages[:-self._window_size] if len(old_messages) > self._window_size else []
        if len(candidates) >= self._summary_batch_size:
            try:
                summary = await self._summarize(provider, summary, candidates)
                covered = int(self._value(candidates[-1], "sequence_num", covered))
                summary = await self._repository.save_summary(db, session_id, summary, covered)
            except Exception as error:
                logger.warning("语音面试摘要失败，降级到 WINDOW: %s", error)
                return self._format(messages[-self._window_size :])

        summary_text = str(self._value(summary, "ai_generated_text", "") or "")
        recent = [m for m in messages if int(self._value(m, "sequence_num", 0)) > covered]
        parts = []
        if summary_text:
            parts.append(f"早期对话摘要：\n{summary_text}")
        if recent:
            parts.append("最近对话：\n" + self._format(recent[-self._window_size :]))
        return "\n\n".join(parts)

    async def _summarize(self, provider: str | None, previous: Any, messages: list[Any]) -> str:
        import asyncio

        previous_text = str(self._value(previous, "ai_generated_text", "") or "暂无")
        source = wrap_prompt_data("conversation", sanitize_prompt_data(self._format(messages)))
        model = await self._resolver.resolve(provider)
        response = await asyncio.wait_for(
            model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "你负责压缩语音面试历史。保留已问主题、候选人的关键观点、"
                            "薄弱点、待追问点和明确要求换题的信息。只输出简洁纯文本摘要。"
                        )
                    ),
                    HumanMessage(content=f"旧摘要：\n{previous_text}\n\n新增对话：\n{source}"),
                ]
            ),
            timeout=self._summary_timeout_seconds,
        )
        return str(getattr(response, "content", response)).strip()

    @classmethod
    def _format(cls, messages: list[Any]) -> str:
        rows: list[str] = []
        for message in messages:
            ai_text = str(cls._value(message, "ai_generated_text", "") or "").strip()
            user_text = str(cls._value(message, "user_recognized_text", "") or "").strip()
            if ai_text:
                rows.append(f"面试官：{ai_text}")
            if user_text:
                rows.append(f"候选人：{sanitize_prompt_data(user_text)}")
        return "\n".join(rows)

    @staticmethod
    def _value(source: Any, name: str, default: Any = None) -> Any:
        if source is None:
            return default
        if hasattr(source, name):
            return getattr(source, name)
        camel = name.split("_")[0] + "".join(part.title() for part in name.split("_")[1:])
        return getattr(source, camel, default)

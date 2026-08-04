from __future__ import annotations

import asyncio
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from common.llm_provider import LlmProviderResolver
from modules.resume.repository.resume_repository import ResumeRepository
from modules.voiceinterview.repository.message_repository import VoiceInterviewMessageRepository
from modules.voiceinterview.service.context_service import VoiceInterviewContextService
from modules.voiceinterview.service.prompt_builder import VoiceInterviewPromptBuilder


class VoiceInterviewConversationService:
    def __init__(
        self,
        prompt_builder: VoiceInterviewPromptBuilder,
        context_service: VoiceInterviewContextService,
        resolver: LlmProviderResolver,
        resume_repository: ResumeRepository,
        message_repository: VoiceInterviewMessageRepository,
        timeout_seconds: float = 30.0,
        max_chars: int = 120,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._context_service = context_service
        self._resolver = resolver
        self._resume_repository = resume_repository
        self._message_repository = message_repository
        self._timeout_seconds = timeout_seconds
        self._max_chars = max(40, max_chars)

    async def generate_opening(self, db: AsyncSession, session: Any) -> str:
        phase_raw = self._value(session, "current_phase", "TECH")
        phase = str(getattr(phase_raw, "value", phase_raw))
        skill_id = str(self._value(session, "skill_id", "java-backend"))
        if phase == "INTRO":
            opening = "你好，我是本场面试官。请先用一分钟介绍一下自己，并重点说明与你应聘方向最相关的经历。"
        else:
            opening = f"你好，我是本场面试官。我们将围绕{skill_id}开始面试，请先介绍一个你深度参与且最能体现技术能力的项目。"
        session_id = int(self._value(session, "id", 0))
        messages = await self._message_repository.list_for_context(db, session_id)
        if messages:
            return ""
        await self._message_repository.append_ai_question(db, session_id, phase, opening)
        await db.commit()
        return opening

    async def generate_reply(
        self, db: AsyncSession, session: Any, user_text: str
    ) -> str:
        session_id = int(self._value(session, "id", 0))
        provider = self._value(session, "llm_provider", None)
        history = await self._context_service.build_context(db, session_id, provider)
        resume_text = ""
        resume_id = self._value(session, "resume_id", None)
        if resume_id is not None:
            resume = await self._resume_repository.find_by_id(db, int(resume_id))
            resume_text = str(getattr(resume, "resumeText", "") or "") if resume else ""
        prompt = self._prompt_builder.build(session, user_text, history, resume_text)
        await self._message_repository.fill_latest_unanswered(db, session_id, user_text)
        # Persist the candidate answer before the external LLM call. This also
        # commits a newly generated SUMMARY, if any.
        await db.commit()
        try:
            model = await self._resolver.resolve(provider)
            response = await asyncio.wait_for(
                model.ainvoke(
                    [SystemMessage(content=prompt.system), HumanMessage(content=prompt.user)]
                ),
                timeout=self._timeout_seconds,
            )
        except BusinessException:
            raise
        except Exception as error:
            raise BusinessException(ErrorCode.AI_SERVICE_ERROR, "语音面试出题失败，请重试") from error
        text = self._clean(str(getattr(response, "content", response)))
        if not text:
            raise BusinessException(ErrorCode.AI_SERVICE_ERROR, "语音面试出题结果为空，请重试")
        await self._message_repository.append_ai_question(
            db, session_id, self._value(session, "current_phase", "TECH"), text
        )
        await db.commit()
        return text

    def _clean(self, value: str) -> str:
        text = re.sub(r"```.*?```", "", value, flags=re.DOTALL)
        text = re.sub(r"(?:^|\n)\s*[-*#>]\s*", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= self._max_chars:
            return text
        shortened = text[: self._max_chars]
        boundary = max(shortened.rfind(mark) for mark in "。！？；")
        return shortened[: boundary + 1] if boundary >= self._max_chars // 2 else shortened.rstrip() + "…"

    @staticmethod
    def _value(source: Any, name: str, default: Any = None) -> Any:
        if hasattr(source, name):
            return getattr(source, name)
        camel = name.split("_")[0] + "".join(part.title() for part in name.split("_")[1:])
        return getattr(source, camel, default)

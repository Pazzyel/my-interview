from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from common.prompt_security import (
    DATA_BOUNDARY_INSTRUCTION,
    sanitize_prompt_data,
    wrap_prompt_data,
)
from modules.interview.service.interview_skill_service import InterviewSkillService


@dataclass(frozen=True)
class VoicePrompt:
    system: str
    user: str


class VoiceInterviewPromptBuilder:
    """Build the voice interviewer prompt without duplicating Skill parsing."""

    def __init__(
        self,
        skill_service: InterviewSkillService,
        prompt_path: Path | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[4]
        path = prompt_path or project_root / "resources" / "prompts" / "voice-interview-system.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self._system_template = str(payload.get("system") or "")
        self._user_template = str(payload.get("user") or "")
        self._skill_service = skill_service

    def build(
        self,
        session: Any,
        current_answer: str,
        history_text: str,
        resume_text: str = "",
    ) -> VoicePrompt:
        skill_id = self._text(self._value(session, "skill_id", "java-backend"))
        skill = self._skill_service.get_skill(skill_id)
        persona = skill.persona or skill.description or skill.name
        difficulty = self._text(self._value(session, "difficulty", "mid"))
        phase = self._text(self._value(session, "current_phase", "TECH"))
        jd = self._safe_block("jd", str(self._value(session, "custom_jd_text", "") or ""))
        resume = self._safe_block("resume", resume_text)
        answer = self._safe_block("answer", current_answer)
        history = self._safe_block("history", history_text)
        system = self._system_template.format(
            skill_id=skill_id,
            skill_name=skill.name,
            skill_persona=persona,
            difficulty=difficulty,
            phase=phase,
            data_boundary_instruction=DATA_BOUNDARY_INSTRUCTION,
        )
        user = self._user_template.format(
            jd=jd or "未提供 JD",
            resume=resume or "未提供简历",
            history=history or "暂无历史对话",
            current_answer=answer,
        )
        return VoicePrompt(system=system, user=user)

    @staticmethod
    def _safe_block(label: str, value: str) -> str:
        if not value or value.isspace():
            return ""
        return wrap_prompt_data(label, sanitize_prompt_data(value))

    @staticmethod
    def _value(source: Any, name: str, default: Any = None) -> Any:
        if hasattr(source, name):
            return getattr(source, name)
        camel = name.split("_")[0] + "".join(part.title() for part in name.split("_")[1:])
        return getattr(source, camel, default)

    @staticmethod
    def _text(value: Any) -> str:
        return str(getattr(value, "value", value))

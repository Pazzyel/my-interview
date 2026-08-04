import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from common.exceptions import BusinessException, ErrorCode
from common.llm_provider import LlmProviderRegistry, LlmProviderResolver
from common.prompt_security import DATA_BOUNDARY_INSTRUCTION, sanitize_prompt_data, wrap_prompt_data
from modules.interview.model.interview_skill_dto import (
    CategoryDTO,
    CategoryListDTO,
    DisplayDTO,
    SkillCategoryDTO,
    SkillDTO,
    SkillPriority,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefMapping:
    ref: str
    shared: bool
    source_skill_id: str


class InterviewSkillService:
    CUSTOM_SKILL_ID = "custom"

    MIN_JD_LENGTH = 50
    MAX_CATEGORY_LABEL_LENGTH = 50
    MAX_CATEGORY_KEY_LENGTH = 50
    MAX_REFERENCE_SECTION_CHARS = 12_000
    MAX_EVALUATION_REFERENCE_SECTION_CHARS = 6_000
    MAX_SINGLE_REFERENCE_CHARS = 3_000

    _FRONT_MATTER_PATTERN = re.compile(
        r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", re.DOTALL
    )
    _SAFE_REFERENCE_PATTERN = re.compile(r"^[a-zA-Z0-9._/-]+$")

    def __init__(
        self,
        skills_root: Path | None = None,
        jd_prompt_path: Path | None = None,
        chat_model: Any | None = None,
        llm_provider_resolver: LlmProviderResolver | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[4]
        self._skills_root = skills_root or project_root / "resources" / "skills"
        self._jd_prompt_path = jd_prompt_path or project_root / "resources" / "prompts" / "jd-parse-system.st"
        self._chat_model = chat_model
        self._llm_provider_resolver = llm_provider_resolver or LlmProviderRegistry()
        self._preset_registry: dict[str, SkillDTO] = {}
        self._reference_cache: dict[Path, str] = {}
        self._category_ref_index: dict[str, RefMapping] = {}
        self._cached_reference_file_list = "（无可用参考文件）"
        self._jd_system_prompt = self._load_text(self._jd_prompt_path, "读取 JD 解析 Prompt 失败")
        self.load_preset_skills()

    def load_preset_skills(self) -> None:
        """Load immutable preset skills and rebuild derived indexes."""
        self._preset_registry.clear()
        self._reference_cache.clear()

        if not self._skills_root.is_dir():
            raise BusinessException(
                ErrorCode.INTERNAL_ERROR, f"Skill 资源目录不存在: {self._skills_root}"
            )

        for skill_file in sorted(self._skills_root.glob("*/SKILL.md"), key=lambda path: path.parent.name):
            skill_id = skill_file.parent.name
            if skill_id == "_shared":
                continue
            skill = self._parse_skill_definition(skill_id, skill_file)
            if not skill.name.strip():
                logger.warning("跳过无效 Skill（缺少 name）: %s", skill_id)
                continue
            self._preset_registry[skill_id] = skill
            logger.info("加载预设 Skill: %s (%s)", skill_id, skill.name)

        logger.info("共加载 %s 个预设 Skill", len(self._preset_registry))
        self._build_category_ref_index()
        self._cached_reference_file_list = self._build_reference_file_list()

    def get_all_skills(self) -> list[SkillDTO]:
        return list(self._preset_registry.values())

    def get_skill(self, skill_id: str) -> SkillDTO:
        skill = self._preset_registry.get(skill_id)
        if skill is None:
            raise BusinessException(ErrorCode.BAD_REQUEST, f"未找到面试主题: {skill_id}")
        return skill

    def build_custom_skill(self, custom_categories: list[CategoryDTO], jd_text: str) -> SkillDTO:
        categories: list[SkillCategoryDTO] = []
        for category in custom_categories:
            if not category.key or not category.label:
                continue
            safe_key = self._sanitize_category_key(category.key)
            safe_label = self._sanitize_category_label(category.label)
            mapping = self._category_ref_index.get(safe_key)
            if mapping is not None:
                if mapping.ref != category.ref or mapping.shared != bool(category.shared):
                    logger.info(
                        "JD 分类 reference 已按本地映射纠正: key=%s, modelRef=%s, "
                        "modelShared=%s, mappedRef=%s, mappedShared=%s",
                        safe_key,
                        category.ref,
                        category.shared,
                        mapping.ref,
                        mapping.shared,
                    )
                ref = mapping.ref
                shared = mapping.shared
            else:
                ref = category.ref
                shared = bool(category.shared)
            categories.append(
                SkillCategoryDTO(
                    key=safe_key,
                    label=safe_label,
                    priority=category.priority,
                    ref=ref,
                    shared=shared,
                )
            )

        matched_count = sum(1 for category in categories if category.ref)
        logger.info("构建自定义 Skill: %s 个分类, %s 个匹配到参考文件", len(categories), matched_count)
        return SkillDTO(
            id=self.CUSTOM_SKILL_ID,
            name="自定义面试（JD 解析）",
            description="基于职位描述提取的面试方向",
            categories=categories,
            is_preset=False,
            source_jd=jd_text,
        )

    async def parse_jd(self, jd_text: str) -> list[CategoryDTO]:
        if jd_text is None or len(jd_text) < self.MIN_JD_LENGTH:
            raise BusinessException(
                ErrorCode.BAD_REQUEST,
                f"JD 内容太少（至少 {self.MIN_JD_LENGTH} 字），请补充后重试",
            )

        logger.info("开始解析 JD，长度: %s", len(jd_text))
        system_prompt = self._jd_system_prompt.replace(
            "{referenceFileList}", self._cached_reference_file_list
        )
        user_prompt = (
            f"{DATA_BOUNDARY_INSTRUCTION}\n职位描述：\n"
            f"{wrap_prompt_data('jd', sanitize_prompt_data(jd_text))}"
        )

        try:
            model = (await self._get_chat_model()).with_structured_output(CategoryListDTO)
            raw_result = await model.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            )
            result = (
                raw_result
                if isinstance(raw_result, CategoryListDTO)
                else CategoryListDTO.model_validate(raw_result)
            )
            if not result.categories:
                raise BusinessException(ErrorCode.AI_SERVICE_ERROR, "JD 解析结果为空，请重试")
            matched_count = sum(1 for category in result.categories if category.ref)
            logger.info("JD 解析完成: %s 个方向, %s 个匹配到参考文件", len(result.categories), matched_count)
            return result.categories
        except BusinessException:
            raise
        except Exception as error:
            logger.error("JD 解析失败: %s", str(error), exc_info=True)
            raise BusinessException(
                ErrorCode.AI_SERVICE_ERROR, "JD 解析失败，请重试或选择预设主题"
            ) from error

    def calculate_allocation(
        self,
        skill_or_categories: str | list[SkillCategoryDTO],
        total_questions: int,
    ) -> dict[str, int]:
        categories = (
            self.get_skill(skill_or_categories).categories
            if isinstance(skill_or_categories, str)
            else skill_or_categories
        )
        always_one = [c for c in categories if c.priority == SkillPriority.ALWAYS_ONE]
        core = [c for c in categories if c.priority == SkillPriority.CORE]
        normal = [c for c in categories if c.priority not in {SkillPriority.ALWAYS_ONE, SkillPriority.CORE}]

        allocation: dict[str, int] = {}
        remaining = max(total_questions, 0)

        for category in always_one:
            if remaining > 0:
                allocation[category.key] = 1
                remaining -= 1
        for category in core:
            if remaining > 0:
                allocation[category.key] = 1
                remaining -= 1
        for category in normal:
            if remaining > 0:
                allocation[category.key] = 1
                remaining -= 1

        while remaining > 0 and (core or normal):
            for category in [*core, *normal]:
                if remaining <= 0:
                    break
                allocation[category.key] = allocation.get(category.key, 0) + 1
                remaining -= 1

        for category in [*core, *normal]:
            allocation.setdefault(category.key, 0)
        logger.debug("题目分配: total=%s, allocation=%s", total_questions, allocation)
        return allocation

    @staticmethod
    def build_allocation_description(
        allocation: dict[str, int], categories: list[SkillCategoryDTO]
    ) -> str:
        rows = []
        for category in categories:
            count = allocation.get(category.key, 0)
            if count > 0:
                rows.append(f"| {category.label} | {count} 题 | {category.priority.value} |")
        return "\n".join(rows) + ("\n" if rows else "")

    def build_reference_section(self, skill: SkillDTO, allocation: dict[str, int]) -> str:
        return self._build_reference_section_internal(
            skill,
            lambda category: allocation.get(category.key, 0) > 0,
            self.MAX_REFERENCE_SECTION_CHARS,
        )

    def build_evaluation_reference_section(self, skill_id: str) -> str:
        return self._build_reference_section_internal(
            self.get_skill(skill_id),
            lambda _category: True,
            self.MAX_EVALUATION_REFERENCE_SECTION_CHARS,
        )

    def build_evaluation_reference_section_safe(self, skill_id: str | None) -> str:
        if not skill_id or not skill_id.strip():
            return ""
        try:
            return self.build_evaluation_reference_section(skill_id)
        except Exception as error:
            logger.warning(
                "加载评估参考基线失败，降级为无参考: skillId=%s, error=%s",
                skill_id,
                str(error),
            )
            return ""

    def _parse_skill_definition(self, skill_id: str, skill_file: Path) -> SkillDTO:
        markdown = self._load_text(skill_file, "读取 Skill 文件失败")
        match = self._FRONT_MATTER_PATTERN.match(markdown)
        if match is None:
            raise BusinessException(
                ErrorCode.BAD_REQUEST, f"Skill 文件格式错误（缺少 front matter）: {skill_file}"
            )

        try:
            front_matter = yaml.safe_load(match.group(1)) or {}
            meta_path = skill_file.parent / "skill.meta.yml"
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            meta = meta or {}
            categories = [
                SkillCategoryDTO.model_validate(category)
                for category in meta.get("categories", []) or []
            ]
            display_data = meta.get("display")
            display = DisplayDTO.model_validate(display_data) if display_data else None
            name = str(front_matter.get("name") or "")
            display_name = str(meta.get("displayName") or name) if name else ""
            return SkillDTO(
                id=skill_id,
                name=display_name,
                description=str(front_matter.get("description") or ""),
                categories=categories,
                is_preset=True,
                persona=match.group(2).strip() or None,
                display=display,
            )
        except (AttributeError, OSError, yaml.YAMLError, ValidationError, TypeError) as error:
            raise BusinessException(
                ErrorCode.INTERNAL_ERROR, f"读取 Skill 配置失败: {skill_id}"
            ) from error

    def _build_category_ref_index(self) -> None:
        self._category_ref_index.clear()
        for skill_id, skill in self._preset_registry.items():
            for category in skill.categories:
                if category.ref and category.key not in self._category_ref_index:
                    self._category_ref_index[category.key] = RefMapping(
                        category.ref, category.shared, skill_id
                    )
        logger.info("构建 category→reference 映射: %s 个条目", len(self._category_ref_index))

    def _build_reference_file_list(self) -> str:
        descriptions: dict[str, str] = {}
        for skill in self._preset_registry.values():
            for category in skill.categories:
                if category.ref and category.ref not in descriptions:
                    scope = "shared" if category.shared else "skill-local"
                    descriptions[category.ref] = (
                        f"| {category.ref} | {scope} | {skill.name} | {category.label} |"
                    )
        if not descriptions:
            return "（无可用参考文件）"
        rows = [
            "| 文件名 | 范围 | 来源 Skill | 覆盖内容 |",
            "|--------|------|-------------|----------|",
            *descriptions.values(),
        ]
        return "\n".join(rows) + "\n"

    def _build_reference_section_internal(
        self,
        skill: SkillDTO,
        category_filter: Callable[[SkillCategoryDTO], bool],
        max_chars: int,
    ) -> str:
        sections: list[str] = []
        current_length = 0
        for category in skill.categories:
            if not category_filter(category) or not category.ref:
                continue
            effective_skill_id = skill.id
            if skill.id == self.CUSTOM_SKILL_ID and not category.shared:
                mapping = self._category_ref_index.get(category.key)
                if mapping is not None:
                    effective_skill_id = mapping.source_skill_id
            content = self._load_reference_content(
                effective_skill_id, category.ref, category.shared
            )
            if not content:
                continue
            section = f"### {category.label} ({category.key})\n{content}"
            separator_length = 2 if sections else 0
            remaining = max_chars - current_length - separator_length
            if remaining <= 0:
                break
            if len(section) > remaining:
                sections.append(section[:remaining] + "\n...（references 已截断）")
                current_length = max_chars
                break
            sections.append(section)
            current_length += separator_length + len(section)
        return "\n\n".join(sections) if sections else "未配置 references。"

    def _load_reference_content(self, skill_id: str, reference_file: str, shared: bool) -> str:
        if not self._is_safe_reference_path(reference_file):
            logger.warning("忽略不安全的 reference 路径: skillId=%s, ref=%s", skill_id, reference_file)
            return ""
        for location in self._resolve_reference_locations(skill_id, reference_file, shared):
            if location not in self._reference_cache:
                self._reference_cache[location] = self._read_reference_content(location)
            content = self._reference_cache[location]
            if content:
                return content
        logger.warning(
            "未找到 reference: skillId=%s, ref=%s, shared=%s", skill_id, reference_file, shared
        )
        return ""

    def _resolve_reference_locations(
        self, skill_id: str, reference_file: str, shared: bool
    ) -> list[Path]:
        locations: list[Path] = []

        def add(path: Path) -> None:
            if path not in locations:
                locations.append(path)

        def add_skill_locations(target_skill_id: str) -> None:
            if target_skill_id and target_skill_id != self.CUSTOM_SKILL_ID:
                add(self._skills_root / target_skill_id / "references" / reference_file)
                add(self._skills_root / target_skill_id / reference_file)

        shared_path = self._skills_root / "_shared" / "references" / reference_file
        if shared:
            add(shared_path)
        add_skill_locations(skill_id)
        if not shared:
            add(shared_path)
        if skill_id == self.CUSTOM_SKILL_ID or shared:
            for preset_skill_id in self._preset_registry:
                add_skill_locations(preset_skill_id)
        return locations

    def _read_reference_content(self, location: Path) -> str:
        if not location.is_file():
            return ""
        try:
            content = location.read_text(encoding="utf-8").strip()
        except OSError as error:
            logger.warning("读取 reference 失败: location=%s, error=%s", location, str(error))
            return ""
        if len(content) > self.MAX_SINGLE_REFERENCE_CHARS:
            return content[: self.MAX_SINGLE_REFERENCE_CHARS] + "\n...（单文件内容已截断）"
        return content

    async def _get_chat_model(self) -> Any:
        return self._chat_model or await self._llm_provider_resolver.resolve(None)

    @classmethod
    def _is_safe_reference_path(cls, reference_file: str) -> bool:
        return (
            ".." not in reference_file
            and not reference_file.startswith(("/", "\\"))
            and cls._SAFE_REFERENCE_PATTERN.fullmatch(reference_file) is not None
        )

    @classmethod
    def _sanitize_category_key(cls, key: str) -> str:
        if not key or key.isspace():
            return "UNKNOWN"
        trimmed = key.strip()[: cls.MAX_CATEGORY_KEY_LENGTH]
        sanitized = re.sub(r"[^A-Z0-9_]", "_", trimmed.upper())
        if not sanitized:
            return "UNKNOWN"
        return sanitized if sanitized[0].isalpha() else f"CAT_{sanitized}"

    @classmethod
    def _sanitize_category_label(cls, label: str) -> str:
        if not label or label.isspace():
            return "未命名"
        return re.sub(r"[\r\n]+", " ", label.strip())[: cls.MAX_CATEGORY_LABEL_LENGTH]

    @staticmethod
    def _load_text(path: Path, error_message: str) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise BusinessException(ErrorCode.INTERNAL_ERROR, f"{error_message}: {path}") from error

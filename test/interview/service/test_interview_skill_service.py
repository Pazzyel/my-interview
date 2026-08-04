import asyncio
from pathlib import Path
from typing import Any

import pytest

from common.exceptions import BusinessException, ErrorCode
from modules.interview.model.interview_skill_dto import (
    CategoryDTO,
    CategoryListDTO,
    SkillCategoryDTO,
    SkillPriority,
)
from modules.interview.service.interview_skill_service import InterviewSkillService


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class FakeStructuredModel:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.messages = None

    async def ainvoke(self, messages: Any) -> Any:
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.result


class FakeChatModel:
    def __init__(self, structured_model: FakeStructuredModel) -> None:
        self.structured_model = structured_model
        self.schema = None

    def with_structured_output(self, schema: Any) -> FakeStructuredModel:
        self.schema = schema
        return self.structured_model


def make_service(chat_model: Any | None = None) -> InterviewSkillService:
    return InterviewSkillService(
        skills_root=PROJECT_ROOT / "resources" / "skills",
        jd_prompt_path=PROJECT_ROOT / "resources" / "prompts" / "jd-parse-system.st",
        chat_model=chat_model,
    )


def create_skill_fixture(root: Path, skill_markdown: str, meta: str = "categories: []\n") -> tuple[Path, Path]:
    skills_root = root / "skills"
    skill_dir = skills_root / "example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_markdown, encoding="utf-8")
    (skill_dir / "skill.meta.yml").write_text(meta, encoding="utf-8")
    prompt_path = root / "jd-parse-system.st"
    prompt_path.write_text("references:\n{referenceFileList}", encoding="utf-8")
    return skills_root, prompt_path


def test_loads_all_preset_skills_in_id_order() -> None:
    service = make_service()

    skills = service.get_all_skills()

    assert len(skills) == 10
    assert [skill.id for skill in skills] == sorted(skill.id for skill in skills)
    java_skill = service.get_skill("java-backend")
    assert java_skill.name == "Java 后端开发"
    assert java_skill.persona is not None and "Java 后端面试官" in java_skill.persona
    assert java_skill.display is not None and java_skill.display.icon == "☕"


def test_rejects_skill_without_front_matter(tmp_path: Path) -> None:
    skills_root, prompt_path = create_skill_fixture(tmp_path, "# invalid")

    with pytest.raises(BusinessException) as error:
        InterviewSkillService(skills_root, prompt_path)

    assert error.value.code == ErrorCode.BAD_REQUEST


def test_skips_skill_without_standard_name(tmp_path: Path) -> None:
    skills_root, prompt_path = create_skill_fixture(
        tmp_path,
        "---\ndescription: missing name\n---\n# persona",
        "displayName: 只有展示名\ncategories: []\n",
    )

    service = InterviewSkillService(skills_root, prompt_path)

    assert service.get_all_skills() == []


def test_unknown_skill_raises_business_error() -> None:
    service = make_service()

    with pytest.raises(BusinessException) as error:
        service.get_skill("not-found")

    assert error.value.code == ErrorCode.BAD_REQUEST


def test_calculate_allocation_prioritizes_always_one_then_core() -> None:
    service = make_service()
    categories = [
        SkillCategoryDTO(key="PROJECT", label="项目", priority=SkillPriority.ALWAYS_ONE),
        SkillCategoryDTO(key="CORE_A", label="核心A", priority=SkillPriority.CORE),
        SkillCategoryDTO(key="CORE_B", label="核心B", priority=SkillPriority.CORE),
        SkillCategoryDTO(key="NORMAL", label="普通", priority=SkillPriority.NORMAL),
    ]

    assert service.calculate_allocation(categories, 2) == {
        "PROJECT": 1,
        "CORE_A": 1,
        "CORE_B": 0,
        "NORMAL": 0,
    }
    assert service.calculate_allocation(categories, 6) == {
        "PROJECT": 1,
        "CORE_A": 2,
        "CORE_B": 2,
        "NORMAL": 1,
    }


def test_builds_shared_and_local_reference_sections() -> None:
    service = make_service()
    java_skill = service.get_skill("java-backend")
    java_section = service.build_reference_section(java_skill, {"JAVA": 1})
    agent_section = service.build_evaluation_reference_section("ai-agent-dev")

    assert "### Java (JAVA)" in java_section
    assert "JVM" in java_section
    assert "### Agent 基础 (AGENT_BASIS)" in agent_section
    assert "Agent Loop" in agent_section
    assert service._load_reference_content("java-backend", "../secret.md", False) == ""
    assert service._load_reference_content("java-backend", "missing.md", False) == ""


def test_combined_reference_section_obeys_evaluation_limit() -> None:
    service = make_service()

    section = service.build_evaluation_reference_section("test-development")

    assert "references 已截断" in section
    assert len(section) <= service.MAX_EVALUATION_REFERENCE_SECTION_CHARS + len(
        "\n...（references 已截断）"
    )


def test_reference_content_is_cached_and_truncated(tmp_path: Path) -> None:
    skills_root, prompt_path = create_skill_fixture(
        tmp_path,
        "---\nname: example\ndescription: demo\n---\n# Persona",
        "categories:\n"
        "  - key: LOCAL\n"
        "    label: Local\n"
        "    priority: CORE\n"
        "    ref: local.md\n",
    )
    reference_path = skills_root / "example" / "local.md"
    reference_path.write_text("x" * 4000, encoding="utf-8")
    service = InterviewSkillService(skills_root, prompt_path)

    first = service.build_evaluation_reference_section("example")
    reference_path.write_text("changed", encoding="utf-8")
    second = service.build_evaluation_reference_section("example")

    assert first == second
    assert "单文件内容已截断" in first


def test_build_custom_skill_sanitizes_and_corrects_reference_mapping() -> None:
    service = make_service()
    custom = service.build_custom_skill(
        [
            CategoryDTO(
                key=" java ",
                label="Java\n核心",
                priority=SkillPriority.CORE,
                ref="wrong.md",
                shared=False,
            ),
            CategoryDTO(
                key="1-new.category",
                label="新方向",
                priority=SkillPriority.NORMAL,
            ),
        ],
        "JD text",
    )

    assert custom.id == "custom"
    assert custom.is_preset is False
    assert custom.categories[0].key == "JAVA"
    assert custom.categories[0].label == "Java 核心"
    assert custom.categories[0].ref == "java.md"
    assert custom.categories[0].shared is True
    assert custom.categories[1].key == "CAT_1_NEW_CATEGORY"


def test_parse_jd_returns_structured_categories_and_wraps_user_data() -> None:
    output = CategoryListDTO(
        categories=[
            CategoryDTO(key="PYTHON_BASIC", label="Python", priority=SkillPriority.CORE)
        ]
    )
    structured_model = FakeStructuredModel(result=output)
    chat_model = FakeChatModel(structured_model)
    service = make_service(chat_model)

    result = asyncio.run(
        service.parse_jd("Python 后端开发岗位，负责服务设计、数据库优化、缓存治理与线上故障处理。" * 2)
    )

    assert result == output.categories
    assert chat_model.schema is CategoryListDTO
    assert structured_model.messages is not None
    assert "data-boundary-" in str(structured_model.messages[1].content)


def test_parse_jd_validates_length_empty_result_and_model_failure() -> None:
    service = make_service(FakeChatModel(FakeStructuredModel(result=CategoryListDTO(categories=[]))))
    with pytest.raises(BusinessException) as short_error:
        asyncio.run(service.parse_jd("too short"))
    assert short_error.value.code == ErrorCode.BAD_REQUEST

    with pytest.raises(BusinessException) as empty_error:
        asyncio.run(service.parse_jd("x" * 50))
    assert empty_error.value.code == ErrorCode.AI_SERVICE_ERROR

    failing = make_service(FakeChatModel(FakeStructuredModel(error=RuntimeError("LLM unavailable"))))
    with pytest.raises(BusinessException) as model_error:
        asyncio.run(failing.parse_jd("x" * 50))
    assert model_error.value.code == ErrorCode.AI_SERVICE_ERROR

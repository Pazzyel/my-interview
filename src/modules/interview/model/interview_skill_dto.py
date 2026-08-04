from enum import Enum

from pydantic import Field

from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class SkillPriority(str, Enum):
    CORE = "CORE"
    NORMAL = "NORMAL"
    ALWAYS_ONE = "ALWAYS_ONE"


class DisplayDTO(BaseCamelSchema):
    icon: str | None = None
    gradient: str | None = None
    icon_bg: str | None = None
    icon_color: str | None = None


class SkillCategoryDTO(BaseCamelSchema):
    key: str
    label: str
    priority: SkillPriority = SkillPriority.NORMAL
    ref: str | None = None
    shared: bool = False


class CategoryDTO(BaseCamelSchema):
    key: str
    label: str
    priority: SkillPriority = SkillPriority.NORMAL
    ref: str | None = None
    shared: bool | None = None


class CategoryListDTO(BaseCamelSchema):
    categories: list[CategoryDTO]


class SkillDTO(BaseCamelSchema):
    id: str
    name: str
    description: str
    categories: list[SkillCategoryDTO]
    is_preset: bool
    source_jd: str | None = None
    persona: str | None = None
    display: DisplayDTO | None = None


class ParseJdRequest(BaseCamelSchema):
    jd_text: str = Field(min_length=1)

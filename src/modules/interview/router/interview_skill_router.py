from fastapi import APIRouter

from common.dependencies import interview_skill_service
from common.models import Result
from modules.interview.model.interview_skill_dto import CategoryDTO, ParseJdRequest, SkillDTO


router = APIRouter(prefix="/api/interview/skills", tags=["Interview Skill"])


@router.get("", response_model=Result[list[SkillDTO]])
async def list_skills() -> Result[list[SkillDTO]]:
    return Result.success(data=interview_skill_service.get_all_skills())


@router.get("/{skill_id}", response_model=Result[SkillDTO])
async def get_skill(skill_id: str) -> Result[SkillDTO]:
    return Result.success(data=interview_skill_service.get_skill(skill_id))


@router.post("/parse-jd", response_model=Result[list[CategoryDTO]])
async def parse_jd(request: ParseJdRequest) -> Result[list[CategoryDTO]]:
    return Result.success(data=await interview_skill_service.parse_jd(request.jd_text))

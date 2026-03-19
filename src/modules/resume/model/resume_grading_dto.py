from typing import List

from pydantic import BaseModel, Field


class ScoreDetailDTO(BaseModel):
    contentScore: int = Field(default=0)
    structureScore: int = Field(default=0)
    skillMatchScore: int = Field(default=0)
    expressionScore: int = Field(default=0)
    projectScore: int = Field(default=0)


class SuggestionDTO(BaseModel):
    category: str = Field(default="项目")
    priority: str = Field(default="中")
    issue: str = Field(default="")
    recommendation: str = Field(default="")


class ResumeAnalysisStructuredResponseDTO(BaseModel):
    overallScore: int = Field(default=0)
    scoreDetail: ScoreDetailDTO = Field(default_factory=ScoreDetailDTO)
    summary: str = Field(default="")
    strengths: List[str] = Field(default_factory=list)
    suggestions: List[SuggestionDTO] = Field(default_factory=list)

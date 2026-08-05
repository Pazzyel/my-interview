from datetime import datetime
from typing import Any

from pydantic import BaseModel

from common.models import AsyncTaskStatus


class ResumeListItemDTO(BaseModel):
    id: int
    filename: str
    fileSize: int
    uploadedAt: datetime
    accessCount: int
    latestScore: int | None = None
    lastAnalyzedAt: datetime | None = None
    interviewCount: int = 0
    analyzeStatus: AsyncTaskStatus
    analyzeError: str | None = None


class ResumeAnalysisHistoryDTO(BaseModel):
    id: int
    overallScore: int | None = None
    contentScore: int | None = None
    structureScore: int | None = None
    skillMatchScore: int | None = None
    expressionScore: int | None = None
    projectScore: int | None = None
    summary: str | None = None
    analyzedAt: datetime
    strengths: list[str]
    suggestions: list[Any]


class ResumeDetailDTO(BaseModel):
    id: int
    filename: str
    fileSize: int
    contentType: str
    storageUrl: str | None = None
    uploadedAt: datetime
    accessCount: int
    resumeText: str | None = None
    analyzeStatus: AsyncTaskStatus
    analyzeError: str | None = None
    analyses: list[ResumeAnalysisHistoryDTO]
    interviews: list[Any]

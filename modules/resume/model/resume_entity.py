from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from common.models import AsyncTaskStatus

class ResumeEntity(BaseModel):
    """
    Resume Entity pure data model for deduplication and persistence
    No ORM features are used here mapping directly from/to dictionary in repository.
    """
    id: Optional[int] = None
    fileHash: str
    originalFilename: str
    fileSize: int
    contentType: str
    storageKey: Optional[str] = None
    storageUrl: Optional[str] = None
    resumeText: Optional[str] = None
    uploadedAt: datetime = Field(default_factory=datetime.now)
    lastAccessedAt: datetime = Field(default_factory=datetime.now)
    accessCount: int = 1
    analyzeStatus: AsyncTaskStatus = AsyncTaskStatus.PENDING
    analyzeError: Optional[str] = None
    
    def increment_access_count(self) -> None:
        self.accessCount += 1
        self.lastAccessedAt = datetime.now()

class ResumeAnalysisEntity(BaseModel):
    """
    Resume Analysis Entity pure data model
    """
    id: Optional[int] = None
    resume_id: int
    overallScore: Optional[int] = None
    contentScore: Optional[int] = None
    structureScore: Optional[int] = None
    skillMatchScore: Optional[int] = None
    expressionScore: Optional[int] = None
    projectScore: Optional[int] = None
    summary: Optional[str] = None
    strengthsJson: Optional[str] = None
    suggestionsJson: Optional[str] = None
    analyzedAt: datetime = Field(default_factory=datetime.now)

class ResumeAnalysisResponse(BaseModel):
    """ DTO for Analysis Response """
    overallScore: Optional[int] = None
    contentScore: Optional[int] = None
    structureScore: Optional[int] = None
    skillMatchScore: Optional[int] = None
    expressionScore: Optional[int] = None
    projectScore: Optional[int] = None
    summary: Optional[str] = None
    strengths: Optional[list[str]] = None
    suggestions: Optional[list[str]] = None

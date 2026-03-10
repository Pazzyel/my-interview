from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, desc
from modules.resume.model.resume_entity import ResumeEntity, ResumeAnalysisResponse
from infrastructure.database.models import ResumeORM, ResumeAnalysisORM
from common.models import AsyncTaskStatus
import json

class ResumeRepository:
    """
    使用SQLAlchemy 2.0 实现Repository
    
    Repository for Resume entity, using SQLAlchemy 2.0 explicitly.
    Uses an injected async database session.
    Converts strictly between ORM entities and pure Data models.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, resume_id: int) -> Optional[ResumeEntity]:
        """Find a resume by ID."""
        stmt = select(ResumeORM).where(ResumeORM.id == resume_id)
        result = await self.db.execute(stmt)
        orm_obj = result.scalar_one_or_none()

        if orm_obj:
            return ResumeEntity(
                id=orm_obj.id,
                fileHash=orm_obj.fileHash,
                originalFilename=orm_obj.originalFilename,
                fileSize=orm_obj.fileSize,
                contentType=orm_obj.contentType,
                storageKey=orm_obj.storageKey,
                storageUrl=orm_obj.storageUrl,
                resumeText=orm_obj.resumeText,
                uploadedAt=orm_obj.uploadedAt,
                lastAccessedAt=orm_obj.lastAccessedAt,
                accessCount=orm_obj.accessCount,
                analyzeStatus=orm_obj.analyzeStatus,
                analyzeError=orm_obj.analyzeError
            )
        return None

    async def find_by_hash(self, file_hash: str) -> Optional[ResumeEntity]:
        """Find an existing resume by file hash."""
        stmt = select(ResumeORM).where(ResumeORM.fileHash == file_hash)
        result = await self.db.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        
        if orm_obj:
            return ResumeEntity(
                id=orm_obj.id,
                fileHash=orm_obj.fileHash,
                originalFilename=orm_obj.originalFilename,
                fileSize=orm_obj.fileSize,
                contentType=orm_obj.contentType,
                storageKey=orm_obj.storageKey,
                storageUrl=orm_obj.storageUrl,
                resumeText=orm_obj.resumeText,
                uploadedAt=orm_obj.uploadedAt,
                lastAccessedAt=orm_obj.lastAccessedAt,
                accessCount=orm_obj.accessCount,
                analyzeStatus=orm_obj.analyzeStatus,
                analyzeError=orm_obj.analyzeError
            )
        return None

    async def save(self, resume: ResumeEntity) -> ResumeEntity:
        """Insert a new resume record."""
        # Convert pure data model to ORM model
        new_resume_orm = ResumeORM(
            fileHash=resume.fileHash,
            originalFilename=resume.originalFilename,
            fileSize=resume.fileSize,
            contentType=resume.contentType,
            storageKey=resume.storageKey,
            storageUrl=resume.storageUrl,
            resumeText=resume.resumeText,
            uploadedAt=resume.uploadedAt,
            lastAccessedAt=resume.lastAccessedAt,
            accessCount=resume.accessCount,
            analyzeStatus=resume.analyzeStatus,
            analyzeError=resume.analyzeError
        )
        
        self.db.add(new_resume_orm)
        await self.db.flush() # Flush to get the generated ID
        await self.db.commit()
        
        resume.id = new_resume_orm.id
        return resume

    async def get_latest_analysis_as_dto(self, resume_id: int) -> Optional[ResumeAnalysisResponse]:
        """Fetch the latest analysis for a given resume ID."""
        stmt = (
            select(ResumeAnalysisORM)
            .where(ResumeAnalysisORM.resume_id == resume_id)
            .order_by(desc(ResumeAnalysisORM.analyzedAt))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        
        if not orm_obj:
            return None
            
        strengths = json.loads(orm_obj.strengthsJson) if orm_obj.strengthsJson else []
        suggestions = json.loads(orm_obj.suggestionsJson) if orm_obj.suggestionsJson else []
        
        return ResumeAnalysisResponse(
            overallScore=orm_obj.overallScore,
            contentScore=orm_obj.contentScore,
            structureScore=orm_obj.structureScore,
            skillMatchScore=orm_obj.skillMatchScore,
            expressionScore=orm_obj.expressionScore,
            projectScore=orm_obj.projectScore,
            summary=orm_obj.summary,
            strengths=strengths,
            suggestions=suggestions
        )

import json
from typing import Dict, Optional

from sqlalchemy import select, desc, update, insert, delete
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import AsyncTaskStatus
from infrastructure.database.models import ResumeORM, ResumeAnalysisORM
from modules.resume.model.resume_entity import ResumeEntity, ResumeAnalysisEntity, ResumeAnalysisResponse


class ResumeRepository:
    """
    使用SQLAlchemy 2.0 实现Repository
    
    Repository for Resume entity, using SQLAlchemy 2.0 explicitly.
    Uses an injected async database session.
    Converts strictly between ORM entities and pure Data models.
    """
    def __init__(self):
        pass

    async def exists_by_id(self, db: AsyncSession, resume_id: int) -> bool:
        """Check if resume exists by id."""
        stmt = select(ResumeORM.id).where(ResumeORM.id == resume_id)
        result = await db.execute(stmt)
        orm_id: Optional[int] = result.scalar_one_or_none()
        return orm_id is not None

    async def find_by_id(self, db: AsyncSession, resume_id: int) -> Optional[ResumeEntity]:
        """Find a resume by ID."""
        stmt = select(ResumeORM).where(ResumeORM.id == resume_id)
        result = await db.execute(stmt)
        orm_obj = result.scalar_one_or_none()

        if orm_obj:
            return self.to_resume_entity(orm_obj)
        return None

    async def find_by_hash(self, db: AsyncSession, file_hash: str) -> Optional[ResumeEntity]:
        """Find an existing resume by file hash."""
        stmt = select(ResumeORM).where(ResumeORM.fileHash == file_hash)
        result = await db.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        
        if orm_obj:
            return self.to_resume_entity(orm_obj)
        return None

    async def find_all_ordered(self, db: AsyncSession) -> list[ResumeEntity]:
        """Find all resumes ordered by upload time desc."""
        stmt = select(ResumeORM).order_by(desc(ResumeORM.uploadedAt))
        result = await db.execute(stmt)
        orm_list: list[ResumeORM] = list(result.scalars().all())
        return [self.to_resume_entity(item) for item in orm_list]

    async def save(self, db: AsyncSession, resume: ResumeEntity) -> ResumeEntity:
        """Insert a new resume record."""
        # Convert pure data model to ORM model
        new_resume_orm = self.to_resume_orm(resume)
        
        db.add(new_resume_orm)
        await db.flush() # Flush to get the generated ID
        
        resume.id = new_resume_orm.id
        return resume

    async def update_analyze_status(
        self,
        db: AsyncSession,
        resume_id: int,
        status: AsyncTaskStatus,
        analyze_error: Optional[str],
    ) -> bool:
        """Update resume analyze status and error message."""
        update_data: Dict[str, Optional[str] | AsyncTaskStatus] = {
            "analyzeStatus": status,
            "analyzeError": analyze_error,
        }
        stmt = update(ResumeORM).where(ResumeORM.id == resume_id).values(**update_data)
        result = await db.execute(stmt)
        row_count: int = int(result.rowcount or 0) # type: ignore
        return row_count > 0

    async def save_analysis(self, db: AsyncSession, analysis: ResumeAnalysisEntity) -> ResumeAnalysisEntity:
        """Insert one resume analysis record."""
        analysis_data: Dict[str, object] = {
            "resume_id": analysis.resume_id,
            "overallScore": analysis.overallScore,
            "contentScore": analysis.contentScore,
            "structureScore": analysis.structureScore,
            "skillMatchScore": analysis.skillMatchScore,
            "expressionScore": analysis.expressionScore,
            "projectScore": analysis.projectScore,
            "summary": analysis.summary,
            "strengthsJson": analysis.strengthsJson,
            "suggestionsJson": analysis.suggestionsJson,
            "analyzedAt": analysis.analyzedAt,
        }
        insert_result = await db.execute(insert(ResumeAnalysisORM).values(**analysis_data))
        analysis_id: int = int(insert_result.inserted_primary_key[0]) # type: ignore
        analysis.id = analysis_id
        return analysis

    async def find_analyses_by_resume_id(self, db: AsyncSession, resume_id: int) -> list[ResumeAnalysisEntity]:
        """Find all analyses by resume id ordered by analyzed time desc."""
        stmt = (
            select(ResumeAnalysisORM)
            .where(ResumeAnalysisORM.resume_id == resume_id)
            .order_by(desc(ResumeAnalysisORM.analyzedAt))
        )
        result = await db.execute(stmt)
        orm_list: list[ResumeAnalysisORM] = list(result.scalars().all())
        return [self.to_analysis_entity(item) for item in orm_list]

    async def get_latest_analysis_as_dto(self, db: AsyncSession, resume_id: int) -> Optional[ResumeAnalysisResponse]:
        """Fetch the latest analysis for a given resume ID."""
        stmt = (
            select(ResumeAnalysisORM)
            .where(ResumeAnalysisORM.resume_id == resume_id)
            .order_by(desc(ResumeAnalysisORM.analyzedAt))
            .limit(1)
        )
        result = await db.execute(stmt)
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

    async def delete_by_id(self, db: AsyncSession, resume_id: int) -> None:
        """Delete resume analysis records then resume itself."""
        await db.execute(delete(ResumeAnalysisORM).where(ResumeAnalysisORM.resume_id == resume_id))
        await db.execute(delete(ResumeORM).where(ResumeORM.id == resume_id))

    def to_resume_entity(self, orm_obj: ResumeORM) -> ResumeEntity:
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

    def to_analysis_entity(self, orm_obj: ResumeAnalysisORM) -> ResumeAnalysisEntity:
        return ResumeAnalysisEntity(
            id=orm_obj.id,
            resume_id=orm_obj.resume_id,
            overallScore=orm_obj.overallScore,
            contentScore=orm_obj.contentScore,
            structureScore=orm_obj.structureScore,
            skillMatchScore=orm_obj.skillMatchScore,
            expressionScore=orm_obj.expressionScore,
            projectScore=orm_obj.projectScore,
            summary=orm_obj.summary,
            strengthsJson=orm_obj.strengthsJson,
            suggestionsJson=orm_obj.suggestionsJson,
            analyzedAt=orm_obj.analyzedAt,
        )

    def to_resume_orm(self, resume: ResumeEntity) -> ResumeORM:
        return ResumeORM(
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
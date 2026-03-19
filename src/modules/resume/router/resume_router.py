import logging
from typing import Dict, Any

from fastapi import APIRouter, File, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.dependencies import resume_upload_service, resume_history_service, resume_delete_service
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.resume.model.resume_history_dto import ResumeDetailDTO, ResumeListItemDTO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resumes", tags=["Resume"])

# 资源上传入口
@router.post("/upload")
async def upload_and_analyze(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_session)
) -> Result[Dict[str, Any]]:
    """
    上传简历并分析

    Upload a resume file and trigger analysis.
    """
    logger.info("Uploading resume...")
    result_data = await resume_upload_service.upload_and_analyze(db, file)
    
    is_duplicate = result_data.get("duplicate", False)
    if is_duplicate:
        return Result.success(data=result_data, message="Same resume detected, returning history analysis result.")
        
    return Result.success(data=result_data)


@router.get("")
async def get_all_resumes(
    db: AsyncSession = Depends(get_async_session),
) -> Result[list[ResumeListItemDTO]]:
    resumes: list[ResumeListItemDTO] = await resume_history_service.get_all_resumes(db)
    return Result.success(data=resumes)


@router.get("/{resume_id}/detail")
async def get_resume_detail(
    resume_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[ResumeDetailDTO]:
    detail: ResumeDetailDTO = await resume_history_service.get_resume_detail(db, resume_id)
    return Result.success(data=detail)


@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    await resume_delete_service.delete_resume(db, resume_id)
    return Result.success(data=None)


@router.post("/{resume_id}/reanalyze")
async def reanalyze(
    resume_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    await resume_upload_service.reanalyze(db, resume_id)
    return Result.success(data=None)

@router.get("/health")
async def health() -> Result[Dict[str, str]]:
    """
    Health check endpoint
    Equivalent to Java: ResumeController.health
    """
    return Result.success(data={
        "status": "UP",
        "service": "AI Interview Platform - Resume Service (Python API)"
    })

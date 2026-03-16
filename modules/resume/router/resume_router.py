import logging
from fastapi import APIRouter, File, UploadFile, Depends
from typing import Dict, Any

from common.models import Result
from common.dependencies import resume_upload_service
from infrastructure.database.connection import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession

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

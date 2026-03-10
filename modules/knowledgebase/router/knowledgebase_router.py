import logging
from fastapi import APIRouter, File, UploadFile, Depends, Form
from typing import Dict, Any, Optional

from common.models import Result
from modules.knowledgebase.service.knowledgebase_upload_service import KnowledgeBaseUploadService
from common.dependencies import get_knowledgebase_upload_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledgebase", tags=["KnowledgeBase"])


@router.post("/upload")
async def upload_knowledge_base(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    category: Optional[str] = Form(default=None),
    upload_service: KnowledgeBaseUploadService = Depends(get_knowledgebase_upload_service),
) -> Result[Dict[str, Any]]:
    """
    上传知识库文件

    Upload a knowledge base file with optional name and category.
    Triggers async vectorization via RocketMQ.
    """
    result_data: Dict[str, Any] = await upload_service.upload_knowledge_base(file, name, category)

    is_duplicate: bool = result_data.get("duplicate", False)
    if is_duplicate:
        return Result.success(data=result_data, message="检测到重复知识库，返回已有记录")

    return Result.success(data=result_data)


@router.post("/{kb_id}/revectorize")
async def revectorize(
    kb_id: int,
    upload_service: KnowledgeBaseUploadService = Depends(get_knowledgebase_upload_service),
) -> Result[None]:
    """
    重新向量化知识库（手动重试）

    Re-vectorize a knowledge base. Used after vectorization failure.
    """
    await upload_service.revectorize(kb_id)
    return Result.success(data=None)

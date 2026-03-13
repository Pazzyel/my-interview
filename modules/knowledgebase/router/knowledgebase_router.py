import logging
from fastapi import APIRouter, File, UploadFile, Depends, Form
from typing import Dict, Any, Optional
from pydantic import BaseModel
from typing import List
from fastapi import Query

from common.exceptions import BusinessException
from common.models import Result
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.model.knowledgebase_dto import KnowledgeBaseListItemDTO, KnowledgeBaseStatsDTO
from common.dependencies import (
    knowledgebase_upload_service,
    knowledgebase_list_service,
    knowledgebase_delete_service,
)
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from common.dependencies import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledgebase", tags=["KnowledgeBase"])


@router.post("/upload")
async def upload_knowledge_base(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    category: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_async_session),
) -> Result[Dict[str, Any]]:
    """
    上传知识库文件

    Upload a knowledge base file with optional name and category.
    Triggers async vectorization via RocketMQ.
    """
    result_data: Dict[str, Any] = await knowledgebase_upload_service.upload_knowledge_base(db, file, name, category)

    is_duplicate: bool = result_data.get("duplicate", False)
    if is_duplicate:
        return Result.success(data=result_data, message="检测到重复知识库，返回已有记录")

    return Result.success(data=result_data)


@router.post("/{kb_id}/revectorize")
async def revectorize(
    kb_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    """
    重新向量化知识库（手动重试）

    Re-vectorize a knowledge base. Used after vectorization failure.
    """
    await knowledgebase_upload_service.revectorize(db, kb_id)
    return Result.success(data=None)

@router.get("/list", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def get_all_knowledge_bases(
    sort_by: Optional[str] = Query(None),
    vector_status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
):
    """获取所有知识库列表 / Get all knowledge bases"""
    status_enum = None
    if vector_status:
        try:
            status_enum = VectorStatus(vector_status.upper())
        except ValueError:
            return Result.error(message=f"无效的向量化状态 / Invalid vector status: {vector_status}")
            
    items = await knowledgebase_list_service.list_knowledge_bases(db, status_enum, sort_by)
    return Result.success(data=items)

@router.get("/categories", response_model=Result[List[str]])
async def get_all_categories(
    db: AsyncSession = Depends(get_async_session),
):
    """获取所有分类 / Get all categories"""
    categories = await knowledgebase_list_service.get_all_categories(db)
    return Result.success(data=categories)

@router.get("/category/{category}", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def get_by_category(
    category: str,
    db: AsyncSession = Depends(get_async_session),
):
    """根据分类获取知识库列表 / Get knowledge bases by category"""
    items = await knowledgebase_list_service.list_by_category(db, category)
    return Result.success(data=items)

@router.get("/uncategorized", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def get_uncategorized(
    db: AsyncSession = Depends(get_async_session),
):
    """获取未分类的知识库 / Get uncategorized knowledge bases"""
    items = await knowledgebase_list_service.list_by_category(db, None)
    return Result.success(data=items)

class CategoryUpdateReq(BaseModel):
    category: str

@router.put("/{kb_id}/category", response_model=Result[None])
async def update_category(
    kb_id: int,
    req: CategoryUpdateReq,
    db: AsyncSession = Depends(get_async_session),
):
    """更新知识库分类 / Update knowledge base category"""
    await knowledgebase_list_service.update_category(db, kb_id, req.category)
    return Result.success(data=None)

@router.get("/search", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def search(
    keyword: str = Query(...),
    db: AsyncSession = Depends(get_async_session),
):
    """搜索知识库 / Search knowledge bases"""
    items = await knowledgebase_list_service.search(db, keyword)
    return Result.success(data=items)

@router.get("/stats", response_model=Result[KnowledgeBaseStatsDTO])
async def get_statistics(
    db: AsyncSession = Depends(get_async_session),
):
    """获取知识库统计信息 / Get knowledge base statistics"""
    stats = await knowledgebase_list_service.get_statistics(db)
    return Result.success(data=stats)
    
@router.get("/{kb_id}", response_model=Result[KnowledgeBaseListItemDTO])
async def get_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_async_session),
):
    """获取知识库详情 / Get knowledge base details"""
    item = await knowledgebase_list_service.get_knowledge_base(db, kb_id)
    if not item:
        return Result.error(message="知识库不存在 / Knowledge base not found")
    return Result.success(data=item)

import urllib.parse

@router.get("/{kb_id}/download")
async def download_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_async_session),
):
    """下载知识库文件 / Download knowledge base file"""
    try:
        entity = await knowledgebase_list_service.get_entity_for_download(db, kb_id)
        content = await knowledgebase_list_service.download_file(db, kb_id)
        
        filename = entity.original_filename
        encoded_filename = urllib.parse.quote(filename.encode('utf-8'))
        
        headers = {
            "Content-Disposition": f"attachment; filename=\"{encoded_filename}\"; filename*=UTF-8''{encoded_filename}"
        }
        content_type = entity.content_type if entity.content_type else "application/octet-stream"
        
        return Response(content=content, media_type=content_type, headers=headers)
    except BusinessException as e:
         return Result.error(message=e.message)

@router.delete("/{kb_id}", response_model=Result[None])
async def delete_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_async_session),
):
    """删除知识库 / Delete knowledge base"""
    await knowledgebase_delete_service.delete_knowledge_base(db, kb_id)
    return Result.success(data=None)


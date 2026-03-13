import logging
from fastapi import APIRouter, File, UploadFile, Depends, Form
from typing import Dict, Any, Optional
from pydantic import BaseModel
from typing import List
from fastapi import Query

from common.exceptions import BusinessException
from common.models import Result
from modules.knowledgebase.service.knowledgebase_upload_service import KnowledgeBaseUploadService
from common.dependencies import get_knowledgebase_upload_service
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.model.knowledgebase_dto import KnowledgeBaseListItemDTO, KnowledgeBaseStatsDTO
from common.dependencies import (
    get_knowledgebase_list_service,
    get_knowledgebase_delete_service,
)
from modules.knowledgebase.service.knowledgebase_list_service import KnowledgeBaseListService
from modules.knowledgebase.service.knowledgebase_delete_service import KnowledgeBaseDeleteService
from fastapi.responses import Response

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

@router.get("/list", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def get_all_knowledge_bases(
    sort_by: Optional[str] = Query(None),
    vector_status: Optional[str] = Query(None),
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """获取所有知识库列表 / Get all knowledge bases"""
    status_enum = None
    if vector_status:
        try:
            status_enum = VectorStatus(vector_status.upper())
        except ValueError:
            return Result.error(message=f"无效的向量化状态 / Invalid vector status: {vector_status}")
            
    items = await list_service.list_knowledge_bases(status_enum, sort_by)
    return Result.success(data=items)

@router.get("/categories", response_model=Result[List[str]])
async def get_all_categories(
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """获取所有分类 / Get all categories"""
    categories = await list_service.get_all_categories()
    return Result.success(data=categories)

@router.get("/category/{category}", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def get_by_category(
    category: str,
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """根据分类获取知识库列表 / Get knowledge bases by category"""
    items = await list_service.list_by_category(category)
    return Result.success(data=items)

@router.get("/uncategorized", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def get_uncategorized(
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """获取未分类的知识库 / Get uncategorized knowledge bases"""
    items = await list_service.list_by_category(None)
    return Result.success(data=items)

class CategoryUpdateReq(BaseModel):
    category: str

@router.put("/{kb_id}/category", response_model=Result[None])
async def update_category(
    kb_id: int,
    req: CategoryUpdateReq,
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """更新知识库分类 / Update knowledge base category"""
    await list_service.update_category(kb_id, req.category)
    return Result.success(data=None)

@router.get("/search", response_model=Result[List[KnowledgeBaseListItemDTO]])
async def search(
    keyword: str = Query(...),
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """搜索知识库 / Search knowledge bases"""
    items = await list_service.search(keyword)
    return Result.success(data=items)

@router.get("/stats", response_model=Result[KnowledgeBaseStatsDTO])
async def get_statistics(
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """获取知识库统计信息 / Get knowledge base statistics"""
    stats = await list_service.get_statistics()
    return Result.success(data=stats)
    
@router.get("/{kb_id}", response_model=Result[KnowledgeBaseListItemDTO])
async def get_knowledge_base(
    kb_id: int,
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """获取知识库详情 / Get knowledge base details"""
    item = await list_service.get_knowledge_base(kb_id)
    if not item:
        return Result.error(message="知识库不存在 / Knowledge base not found")
    return Result.success(data=item)

import urllib.parse

@router.get("/{kb_id}/download")
async def download_knowledge_base(
    kb_id: int,
    list_service: KnowledgeBaseListService = Depends(get_knowledgebase_list_service)
):
    """下载知识库文件 / Download knowledge base file"""
    try:
        entity = await list_service.get_entity_for_download(kb_id)
        content = await list_service.download_file(kb_id)
        
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
    delete_service: KnowledgeBaseDeleteService = Depends(get_knowledgebase_delete_service)
):
    """删除知识库 / Delete knowledge base"""
    await delete_service.delete_knowledge_base(kb_id)
    return Result.success(data=None)


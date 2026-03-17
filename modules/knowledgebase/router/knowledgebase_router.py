import logging
from fastapi import APIRouter, File, UploadFile, Depends, Form
from typing import Dict, Any, Optional
from typing import List
from fastapi import Query
from fastapi.responses import StreamingResponse

from common.exceptions import BusinessException
from common.models import Result
from infrastructure.model.BaseCamelSchema import BaseCamelSchema
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.model.knowledgebase_dto import KnowledgeBaseListItemDTO, KnowledgeBaseStatsDTO
from common.dependencies import (
    knowledgebase_upload_service,
    knowledgebase_list_service,
    knowledgebase_delete_service, knowledgebase_query_service,
)
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_async_session
from modules.knowledgebase.model.query_request import QueryRequest
from modules.knowledgebase.model.query_response import QueryResponse

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
    sortBy: Optional[str] = Query(None),
    vectorStatus: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
):
    """获取所有知识库列表 / Get all knowledge bases"""
    status_enum = None
    if vectorStatus:
        try:
            status_enum = VectorStatus(vectorStatus.upper())
        except ValueError:
            return Result.error(message=f"无效的向量化状态 / Invalid vector status: {vectorStatus}")
            
    items = await knowledgebase_list_service.list_knowledge_bases(db, status_enum, sortBy)
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

class CategoryUpdateReq(BaseCamelSchema):
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

@router.post("/query", response_model=Result[QueryResponse])
async def query_knowledge_base(
    request: QueryRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """基于知识库回答问题（支持多知识库）"""
    data: QueryResponse = await knowledgebase_query_service.query_knowledge_base(db, request)
    return Result.success(data=data)

@router.post("/query/stream", response_model=StreamingResponse)
async def query_knowledge_base_stream(
    request: QueryRequest,
):
    """基于知识库回答问题（流式输出，不会更新知识库计数）"""
    return StreamingResponse(
        knowledgebase_query_service.answer_question_stream(request.question, request.knowledge_base_ids),
        media_type="text/event-stream"
    )
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.dependencies import rag_chat_session_service
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.knowledgebase.model.rag_chat_session_dto import (
    CreateSessionRequest,
    SessionDTO,
    SessionDetailDTO,
    SessionListItemDTO,
    SendMessageRequest,
    UpdateKnowledgeBasesRequest,
    UpdateTitleRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag-chat", tags=["RagChat"])


@router.post("/sessions", response_model=Result[SessionDTO])
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[SessionDTO]:
    logger.info("Request arrived: POST /api/rag-chat/sessions")
    data: SessionDTO = await rag_chat_session_service.create_session(db, request)
    return Result.success(data=data)


@router.get("/sessions", response_model=Result[list[SessionListItemDTO]])
async def list_sessions(
    db: AsyncSession = Depends(get_async_session),
) -> Result[list[SessionListItemDTO]]:
    logger.info("Request arrived: GET /api/rag-chat/sessions")
    data: list[SessionListItemDTO] = await rag_chat_session_service.list_sessions(db)
    return Result.success(data=data)


@router.get("/sessions/{session_id}", response_model=Result[SessionDetailDTO])
async def get_session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[SessionDetailDTO]:
    logger.info("Request arrived: GET /api/rag-chat/sessions/%s", session_id)
    data: SessionDetailDTO = await rag_chat_session_service.get_session_detail(db, session_id)
    return Result.success(data=data)


@router.put("/sessions/{session_id}/title", response_model=Result[None])
async def update_session_title(
    session_id: int,
    request: UpdateTitleRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    logger.info("Request arrived: PUT /api/rag-chat/sessions/%s/title", session_id)
    await rag_chat_session_service.update_session_title(db, session_id, request.title)
    return Result.success(data=None)


@router.put("/sessions/{session_id}/pin", response_model=Result[None])
async def toggle_pin(
    session_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    logger.info("Request arrived: PUT /api/rag-chat/sessions/%s/pin", session_id)
    await rag_chat_session_service.toggle_pin(db, session_id)
    return Result.success(data=None)


@router.put("/sessions/{session_id}/knowledge-bases", response_model=Result[None])
async def update_session_knowledge_bases(
    session_id: int,
    request: UpdateKnowledgeBasesRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    logger.info("Request arrived: PUT /api/rag-chat/sessions/%s/knowledge-bases", session_id)
    await rag_chat_session_service.update_session_knowledge_bases(db, session_id, request.knowledge_base_ids)
    return Result.success(data=None)


@router.delete("/sessions/{session_id}", response_model=Result[None])
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    logger.info("Request arrived: DELETE /api/rag-chat/sessions/%s", session_id)
    await rag_chat_session_service.delete_session(db, session_id)
    return Result.success(data=None)


@router.post("/sessions/{session_id}/messages/stream", response_model=None)
async def send_message_stream(
    session_id: int,
    request: SendMessageRequest,
    db: AsyncSession = Depends(get_async_session),
):
    logger.info("Request arrived: POST /api/rag-chat/sessions/%s/messages/stream", session_id)
    return StreamingResponse(
        rag_chat_session_service.send_message_stream(db, session_id, request.question),
        media_type="text/event-stream",
    )

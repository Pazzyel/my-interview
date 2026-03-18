from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.dependencies import interview_history_service, interview_persistence_service
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.interview.model.interview_dto import InterviewDetailDTO
from modules.interview.model.interview_entity import InterviewSessionEntity

router = APIRouter(prefix="/api/interview", tags=["Interview"])


@router.get("/sessions/unfinished/{resume_id}", response_model=Result[InterviewSessionEntity])
async def find_unfinished_session(
    resume_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewSessionEntity]:
    session: InterviewSessionEntity = await interview_persistence_service.find_unfinished_session_or_throw(db, resume_id)
    return Result.success(data=session)


@router.get("/sessions/{session_id}/details", response_model=Result[InterviewDetailDTO])
async def get_interview_detail(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewDetailDTO]:
    detail: InterviewDetailDTO = await interview_history_service.get_interview_detail(db, session_id)
    return Result.success(data=detail)


@router.delete("/sessions/{session_id}", response_model=Result[None])
async def delete_interview(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    await interview_persistence_service.delete_session_by_session_id(db, session_id)
    return Result.success(data=None)

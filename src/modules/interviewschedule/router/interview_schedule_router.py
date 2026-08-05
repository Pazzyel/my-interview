from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.dependencies import interview_parse_service, interview_schedule_service
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.interviewschedule.model import (
    CreateInterviewRequest,
    InterviewScheduleDTO,
    InterviewStatus,
    ParseRequest,
    ParseResponse,
)

router = APIRouter(prefix="/api/interview-schedule", tags=["Interview Schedule"])


@router.post("/parse")
async def parse_interview(request: ParseRequest) -> Result[ParseResponse]:
    return Result.success(await interview_parse_service.parse(request.raw_text, request.source))


@router.post("")
async def create_interview(
    request: CreateInterviewRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewScheduleDTO]:
    return Result.success(await interview_schedule_service.create(db, request))


@router.get("/{schedule_id}")
async def get_interview(
    schedule_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewScheduleDTO]:
    return Result.success(await interview_schedule_service.get_by_id(db, schedule_id))


@router.get("")
async def get_interviews(
    status: InterviewStatus | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_async_session),
) -> Result[list[InterviewScheduleDTO]]:
    return Result.success(await interview_schedule_service.get_all(db, status, start, end))


@router.put("/{schedule_id}")
async def update_interview(
    schedule_id: int,
    request: CreateInterviewRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewScheduleDTO]:
    return Result.success(await interview_schedule_service.update(db, schedule_id, request))


@router.delete("/{schedule_id}")
async def delete_interview(
    schedule_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    await interview_schedule_service.delete(db, schedule_id)
    return Result.success(None)


@router.patch("/{schedule_id}/status")
async def update_interview_status(
    schedule_id: int,
    status: InterviewStatus,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewScheduleDTO]:
    return Result.success(await interview_schedule_service.update_status(db, schedule_id, status))

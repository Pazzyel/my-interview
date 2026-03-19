import urllib.parse

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.dependencies import interview_agent_service, interview_history_service, interview_persistence_service
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.interview.model.interview_agent_dto import (
    CreateInterviewRequest,
    CurrentQuestionResponse,
    InterviewReportDTO,
    InterviewSessionDTO,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from modules.interview.model.interview_dto import InterviewDetailDTO
from modules.interview.model.interview_entity import InterviewSessionEntity

router = APIRouter(prefix="/api/interview", tags=["Interview"])


@router.post("/sessions", response_model=Result[InterviewSessionDTO])
async def create_session(
    request: CreateInterviewRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewSessionDTO]:
    session: InterviewSessionDTO = await interview_agent_service.create_session(db, request)
    return Result.success(data=session)


@router.get("/sessions/{session_id}", response_model=Result[InterviewSessionDTO])
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewSessionDTO]:
    session: InterviewSessionDTO = await interview_agent_service.get_session(db, session_id)
    return Result.success(data=session)


@router.get("/sessions/{session_id}/question", response_model=Result[CurrentQuestionResponse])
async def get_current_question(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> Result[CurrentQuestionResponse]:
    response: CurrentQuestionResponse = await interview_agent_service.get_current_question(db, session_id)
    return Result.success(data=response)


@router.post("/sessions/{session_id}/answers", response_model=Result[SubmitAnswerResponse])
async def submit_answer(
    session_id: str,
    request: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[SubmitAnswerResponse]:
    response: SubmitAnswerResponse = await interview_agent_service.submit_answer(db, session_id, request)
    return Result.success(data=response)


@router.put("/sessions/{session_id}/answers", response_model=Result[None])
async def save_answer(
    session_id: str,
    request: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    await interview_agent_service.save_answer(db, session_id, request)
    return Result.success(data=None)


@router.post("/sessions/{session_id}/complete", response_model=Result[None])
async def complete_interview(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> Result[None]:
    await interview_agent_service.complete_interview(db, session_id)
    return Result.success(data=None)


@router.get("/sessions/{session_id}/report", response_model=Result[InterviewReportDTO])
async def get_report(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewReportDTO]:
    report: InterviewReportDTO = await interview_agent_service.generate_report(db, session_id)
    return Result.success(data=report)


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


@router.get("/sessions/{session_id}/export")
async def export_report_pdf(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    filename, content = await interview_agent_service.export_report_pdf(db, session_id)
    encoded_filename: str = urllib.parse.quote(filename.encode("utf-8"))
    headers: dict[str, str] = {
        "Content-Disposition": f"attachment; filename=\"{encoded_filename}\"; filename*=UTF-8''{encoded_filename}"
    }
    return Response(content=content, media_type="application/pdf", headers=headers)

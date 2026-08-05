from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.dependencies import knowledgebase_interview_service, knowledgebase_question_service
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.interview.model.interview_agent_dto import InterviewSessionDTO
from modules.knowledgebase.model.knowledgebase_question import (
    CategoryCount,
    CreateKnowledgeBaseInterviewRequest,
    GenerateKnowledgeBaseQuestionsRequest,
    KnowledgeBaseInterviewCapacityResponse,
    KnowledgeBaseQuestionDTO,
    KnowledgeBaseQuestionStatus,
    QuestionGenStatusResponse,
    SaveKnowledgeBaseQuestionRequest,
    UpdateKnowledgeBaseQuestionRequest,
    UpdateKnowledgeBaseQuestionStatusRequest,
)

router = APIRouter(tags=["KnowledgeBaseInterview"])


@router.get("/api/knowledgebase/{kb_id}/questions", response_model=Result[list[KnowledgeBaseQuestionDTO]])
async def list_questions(
    kb_id: int,
    status: KnowledgeBaseQuestionStatus | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_async_session),
) -> Result[list[KnowledgeBaseQuestionDTO]]:
    data = await knowledgebase_question_service.list_questions(
        db, kb_id, status, category, difficulty, keyword
    )
    return Result.success(data=data)


@router.get("/api/knowledgebase/{kb_id}/questions/categories", response_model=Result[list[CategoryCount]])
async def list_categories(
    kb_id: int, db: AsyncSession = Depends(get_async_session)
) -> Result[list[CategoryCount]]:
    return Result.success(data=await knowledgebase_question_service.list_categories(db, kb_id))


@router.post(
    "/api/knowledgebase/{kb_id}/questions/generate",
    response_model=Result[QuestionGenStatusResponse],
)
async def generate_questions(
    kb_id: int,
    request: GenerateKnowledgeBaseQuestionsRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[QuestionGenStatusResponse]:
    return Result.success(
        data=await knowledgebase_question_service.submit_generation_task(db, kb_id, request)
    )


@router.get(
    "/api/knowledgebase/{kb_id}/questions/generation-status",
    response_model=Result[QuestionGenStatusResponse],
)
async def get_generation_status(
    kb_id: int, db: AsyncSession = Depends(get_async_session)
) -> Result[QuestionGenStatusResponse]:
    return Result.success(
        data=await knowledgebase_question_service.get_generation_status(db, kb_id)
    )


@router.post("/api/knowledgebase/{kb_id}/questions", response_model=Result[KnowledgeBaseQuestionDTO])
async def create_question(
    kb_id: int,
    request: SaveKnowledgeBaseQuestionRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[KnowledgeBaseQuestionDTO]:
    return Result.success(data=await knowledgebase_question_service.create_question(db, kb_id, request))


@router.put("/api/knowledgebase/questions/{question_id}", response_model=Result[KnowledgeBaseQuestionDTO])
async def update_question(
    question_id: int,
    request: UpdateKnowledgeBaseQuestionRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[KnowledgeBaseQuestionDTO]:
    return Result.success(data=await knowledgebase_question_service.update_question(db, question_id, request))


@router.put(
    "/api/knowledgebase/questions/{question_id}/status",
    response_model=Result[KnowledgeBaseQuestionDTO],
)
async def update_question_status(
    question_id: int,
    request: UpdateKnowledgeBaseQuestionStatusRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[KnowledgeBaseQuestionDTO]:
    return Result.success(
        data=await knowledgebase_question_service.update_status(db, question_id, request.status)
    )


@router.delete("/api/knowledgebase/questions/{question_id}", response_model=Result[None])
async def delete_question(
    question_id: int, db: AsyncSession = Depends(get_async_session)
) -> Result[None]:
    await knowledgebase_question_service.delete_question(db, question_id)
    return Result.success(data=None)


@router.get(
    "/api/knowledgebase/{kb_id}/interview-capacity",
    response_model=Result[KnowledgeBaseInterviewCapacityResponse],
)
async def get_interview_capacity(
    kb_id: int,
    category: str | None = None,
    difficulty: str = "mid",
    main_question_count: int = Query(default=5, alias="mainQuestionCount", ge=1, le=20),
    db: AsyncSession = Depends(get_async_session),
) -> Result[KnowledgeBaseInterviewCapacityResponse]:
    return Result.success(data=await knowledgebase_interview_service.get_capacity(
        db, kb_id, category, difficulty, main_question_count
    ))


@router.post(
    "/api/knowledgebase-interviews/sessions", response_model=Result[InterviewSessionDTO]
)
async def create_interview_session(
    request: CreateKnowledgeBaseInterviewRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Result[InterviewSessionDTO]:
    return Result.success(data=await knowledgebase_interview_service.create_session(db, request))

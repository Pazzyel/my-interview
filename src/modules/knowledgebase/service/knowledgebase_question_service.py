from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_question import (
    CategoryCount,
    GenerateKnowledgeBaseQuestionsRequest,
    KnowledgeBaseQuestionDTO,
    KnowledgeBaseQuestionEntity,
    KnowledgeBaseQuestionStatus,
    QuestionGenStatusResponse,
    QuestionGenerationConfig,
    SaveKnowledgeBaseQuestionRequest,
    UpdateKnowledgeBaseQuestionRequest,
)
from modules.knowledgebase.repository.knowledgebase_question_repository import (
    KnowledgeBaseQuestionRepository,
)
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.service.question_generation_state_service import (
    QuestionGenerationStateService,
)


def _trim(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


class KnowledgeBaseQuestionService:
    def __init__(
        self,
        knowledgebase_repository: KnowledgeBaseRepository,
        question_repository: KnowledgeBaseQuestionRepository,
        state_service: QuestionGenerationStateService,
        producer: Any,
    ) -> None:
        self.knowledgebase_repository = knowledgebase_repository
        self.question_repository = question_repository
        self.state_service = state_service
        self.producer = producer

    async def list_questions(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        status: KnowledgeBaseQuestionStatus | None,
        category: str | None,
        difficulty: str | None,
        keyword: str | None,
    ) -> list[KnowledgeBaseQuestionDTO]:
        items = await self.question_repository.list_questions(
            db, knowledge_base_id, status, category, difficulty, keyword
        )
        return [KnowledgeBaseQuestionDTO.model_validate(item) for item in items]

    async def list_categories(
        self, db: AsyncSession, knowledge_base_id: int
    ) -> list[CategoryCount]:
        return await self.question_repository.list_categories(db, knowledge_base_id)

    async def create_question(
        self, db: AsyncSession, knowledge_base_id: int, request: SaveKnowledgeBaseQuestionRequest
    ) -> KnowledgeBaseQuestionDTO:
        kb = await self.knowledgebase_repository.find_by_id(db, knowledge_base_id)
        if kb is None:
            raise BusinessException(ErrorCode.KB_NOT_FOUND, "知识库不存在")
        now = datetime.now()
        entity = KnowledgeBaseQuestionEntity(
            knowledge_base_id=knowledge_base_id,
            knowledge_base_name=kb.name,
            difficulty=_trim(request.difficulty) or "mid",
            type=_trim(request.type),
            category=request.category.strip(),
            question=request.question.strip(),
            topic_summary=_trim(request.topic_summary),
            reference_answer=_trim(request.reference_answer),
            key_points=self._clean_strings(request.key_points),
            scoring_rubric=_trim(request.scoring_rubric),
            follow_ups=self._clean_follow_ups(request.follow_ups),
            source_context=_trim(request.source_context),
            kb_content_hash=kb.file_hash,
            status=request.status or KnowledgeBaseQuestionStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        saved = await self.question_repository.save(db, entity)
        return KnowledgeBaseQuestionDTO.model_validate(saved)

    async def update_question(
        self, db: AsyncSession, question_id: int, request: UpdateKnowledgeBaseQuestionRequest
    ) -> KnowledgeBaseQuestionDTO:
        entity = await self._get_question(db, question_id)
        supplied = request.model_fields_set
        if "difficulty" in supplied:
            entity.difficulty = _trim(request.difficulty) or "mid"
        for field in (
            "type", "topic_summary", "reference_answer", "scoring_rubric",
            "source_context", "status",
        ):
            if field in supplied:
                value = getattr(request, field)
                setattr(entity, field, _trim(value) if isinstance(value, str) else value)
        if "category" in supplied:
            if not request.category or not request.category.strip():
                raise BusinessException(ErrorCode.BAD_REQUEST, "面试方向不能为空")
            entity.category = request.category.strip()
        if "question" in supplied:
            if not request.question or not request.question.strip():
                raise BusinessException(ErrorCode.BAD_REQUEST, "题干不能为空")
            entity.question = request.question.strip()
        if request.key_points is not None:
            entity.key_points = self._clean_strings(request.key_points)
        if request.follow_ups is not None:
            entity.follow_ups = self._clean_follow_ups(request.follow_ups)
        entity.updated_at = datetime.now()
        saved = await self.question_repository.save(db, entity)
        return KnowledgeBaseQuestionDTO.model_validate(saved)

    async def update_status(
        self, db: AsyncSession, question_id: int, status: KnowledgeBaseQuestionStatus
    ) -> KnowledgeBaseQuestionDTO:
        return await self.update_question(
            db, question_id, UpdateKnowledgeBaseQuestionRequest(status=status)
        )

    async def delete_question(self, db: AsyncSession, question_id: int) -> None:
        if not await self.question_repository.delete_by_id(db, question_id):
            raise BusinessException(ErrorCode.INTERVIEW_QUESTION_NOT_FOUND, "面试题目不存在")

    async def submit_generation_task(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        request: GenerateKnowledgeBaseQuestionsRequest,
    ) -> QuestionGenStatusResponse:
        config = QuestionGenerationConfig(
            difficulty=request.difficulty.strip() or "mid",
            question_count=request.question_count,
            follow_up_count=request.follow_up_count,
            category_limit=request.category_limit,
            llm_provider=_trim(request.llm_provider),
        )
        response = await self.state_service.create_task(db, knowledge_base_id, config)
        await db.commit()
        self.producer.send_generate_task(knowledge_base_id, response.question_gen_task_id or "")
        return response

    async def get_generation_status(
        self, db: AsyncSession, knowledge_base_id: int
    ) -> QuestionGenStatusResponse:
        return await self.state_service.get_status(db, knowledge_base_id)

    async def _get_question(
        self, db: AsyncSession, question_id: int
    ) -> KnowledgeBaseQuestionEntity:
        entity = await self.question_repository.find_by_id(db, question_id)
        if entity is None:
            raise BusinessException(ErrorCode.INTERVIEW_QUESTION_NOT_FOUND, "面试题目不存在")
        return entity

    @staticmethod
    def _clean_strings(values: list[str]) -> list[str]:
        return [item.strip() for item in values if item and item.strip()]

    @classmethod
    def _clean_follow_ups(cls, values: list[Any]) -> list[Any]:
        result = []
        for item in values:
            if item and item.question and item.question.strip():
                result.append(item.model_copy(update={
                    "question": item.question.strip(),
                    "reference_answer": _trim(item.reference_answer),
                    "key_points": cls._clean_strings(item.key_points),
                    "scoring_rubric": _trim(item.scoring_rubric),
                }))
        return result

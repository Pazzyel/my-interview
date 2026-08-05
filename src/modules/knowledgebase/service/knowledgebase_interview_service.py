import random
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.interview.model.interview_agent_dto import InterviewQuestionDTO, InterviewSessionDTO
from modules.interview.service.interview_agent_service import InterviewAgentService
from modules.knowledgebase.model.knowledgebase_question import (
    CreateKnowledgeBaseInterviewRequest,
    InterviewCategoryCapacity,
    InterviewFollowUpCapacity,
    KnowledgeBaseInterviewCapacityResponse,
    KnowledgeBaseQuestionEntity,
)
from modules.knowledgebase.repository.knowledgebase_question_repository import (
    KnowledgeBaseQuestionRepository,
)
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository


class KnowledgeBaseInterviewService:
    def __init__(
        self,
        knowledgebase_repository: KnowledgeBaseRepository,
        question_repository: KnowledgeBaseQuestionRepository,
        interview_agent_service: InterviewAgentService,
    ) -> None:
        self.knowledgebase_repository = knowledgebase_repository
        self.question_repository = question_repository
        self.interview_agent_service = interview_agent_service

    async def get_capacity(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        category: str | None,
        difficulty: str,
        main_question_count: int,
    ) -> KnowledgeBaseInterviewCapacityResponse:
        await self._require_kb(db, knowledge_base_id)
        normalized_category = self._trim(category)
        normalized_difficulty = self._trim(difficulty) or "mid"
        all_questions = await self.question_repository.list_active(
            db, knowledge_base_id, normalized_difficulty
        )
        scoped = [
            item for item in all_questions
            if normalized_category is None or item.category == normalized_category
        ]
        category_counts = Counter(item.category for item in all_questions if item.category)
        categories = [
            InterviewCategoryCapacity(category=name, available_question_count=count)
            for name, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        follow_up_options = []
        for count in range(6):
            available = sum(1 for item in scoped if len(self._usable_follow_ups(item)) >= count)
            follow_up_options.append(InterviewFollowUpCapacity(
                follow_up_count=count,
                available_question_count=available,
                selectable=main_question_count > 0 and available >= main_question_count,
            ))
        return KnowledgeBaseInterviewCapacityResponse(
            knowledge_base_id=knowledge_base_id,
            category=normalized_category,
            difficulty=normalized_difficulty,
            main_question_count=main_question_count,
            categories=categories,
            follow_up_options=follow_up_options,
        )

    async def create_session(
        self, db: AsyncSession, request: CreateKnowledgeBaseInterviewRequest
    ) -> InterviewSessionDTO:
        await self._require_kb(db, request.knowledge_base_id)
        category = self._trim(request.category)
        difficulty = self._trim(request.difficulty) or "mid"
        raw = await self.question_repository.list_active(
            db, request.knowledge_base_id, difficulty, category
        )
        candidates = [
            item for item in raw
            if len(self._usable_follow_ups(item)) >= request.follow_up_count
        ]
        if len(candidates) < request.main_question_count:
            direction = category or "全部方向"
            raise BusinessException(
                ErrorCode.INTERVIEW_QUESTION_INSUFFICIENT,
                f"需要 {request.main_question_count} 道主问题，但只有 {len(candidates)} 道同时满足："
                f"方向={direction}、难度={difficulty}、每题至少 {request.follow_up_count} 个追问",
            )
        selected = random.sample(candidates, request.main_question_count)
        questions: list[InterviewQuestionDTO] = []
        for source in selected:
            main_index = len(questions)
            questions.append(InterviewQuestionDTO(
                question_index=main_index,
                question=source.question,
                type=source.type or "KNOWLEDGE_BASE",
                category=source.category or "知识库",
                topic_summary=source.topic_summary,
                reference_answer=source.reference_answer,
                key_points=source.key_points,
                scoring_rubric=source.scoring_rubric,
                source_context=source.source_context,
            ))
            usable = self._usable_follow_ups(source)
            picked = random.sample(usable, request.follow_up_count)
            for follow_up in picked:
                questions.append(InterviewQuestionDTO(
                    question_index=len(questions),
                    question=follow_up.question,
                    type=source.type or "KNOWLEDGE_BASE",
                    category=source.category or "知识库追问",
                    topic_summary=source.topic_summary,
                    is_follow_up=True,
                    parent_question_index=main_index,
                    reference_answer=follow_up.reference_answer,
                    key_points=follow_up.key_points,
                    scoring_rubric=follow_up.scoring_rubric,
                    source_context=source.source_context,
                ))
        return await self.interview_agent_service.create_session_from_questions(
            db,
            questions,
            request.llm_provider,
            "knowledge-base",
            difficulty,
            request.knowledge_base_id,
            category,
        )

    async def _require_kb(self, db: AsyncSession, knowledge_base_id: int) -> None:
        if await self.knowledgebase_repository.find_by_id(db, knowledge_base_id) is None:
            raise BusinessException(ErrorCode.KB_NOT_FOUND, "知识库不存在")

    @staticmethod
    def _usable_follow_ups(question: KnowledgeBaseQuestionEntity):
        return [item for item in question.follow_ups if item.question and item.question.strip()]

    @staticmethod
    def _trim(value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

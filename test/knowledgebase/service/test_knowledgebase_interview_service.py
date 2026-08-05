import asyncio
from unittest.mock import AsyncMock

import pytest

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity
from modules.knowledgebase.model.knowledgebase_question import (
    CreateKnowledgeBaseInterviewRequest,
    KnowledgeBaseQuestionEntity,
    KnowledgeBaseQuestionFollowUpDTO,
)
from modules.knowledgebase.service.knowledgebase_interview_service import KnowledgeBaseInterviewService


def _question(category: str, followups: int) -> KnowledgeBaseQuestionEntity:
    return KnowledgeBaseQuestionEntity(
        id=1, knowledge_base_id=1, category=category, difficulty="mid", question=f"{category} 主问题",
        follow_ups=[KnowledgeBaseQuestionFollowUpDTO(question=f"追问 {index}") for index in range(followups)],
    )


def test_capacity_is_strict_and_session_preserves_parent_indexes() -> None:
    async def scenario() -> None:
        kb_repo = AsyncMock()
        kb_repo.find_by_id.return_value = KnowledgeBaseEntity(id=1)
        question_repo = AsyncMock()
        question_repo.list_active.return_value = [_question("Redis", 3), _question("MySQL", 1)]
        interview_service = AsyncMock()
        interview_service.create_session_from_questions.return_value = object()
        service = KnowledgeBaseInterviewService(kb_repo, question_repo, interview_service)

        capacity = await service.get_capacity(object(), 1, None, "mid", 2)
        option_two = next(item for item in capacity.follow_up_options if item.follow_up_count == 2)
        assert option_two.available_question_count == 1
        assert not option_two.selectable

        question_repo.list_active.return_value = [_question("Redis", 3)]
        request = CreateKnowledgeBaseInterviewRequest(
            knowledgeBaseId=1, difficulty="mid", mainQuestionCount=1, followUpCount=2
        )
        await service.create_session(object(), request)
        questions = interview_service.create_session_from_questions.await_args.args[1]
        assert len(questions) == 3
        assert questions[0].question_index == 0
        assert all(item.parent_question_index == 0 for item in questions[1:])

    asyncio.run(scenario())


def test_create_rejects_insufficient_followup_capacity() -> None:
    async def scenario() -> None:
        kb_repo = AsyncMock()
        kb_repo.find_by_id.return_value = KnowledgeBaseEntity(id=1)
        question_repo = AsyncMock()
        question_repo.list_active.return_value = [_question("Redis", 1)]
        service = KnowledgeBaseInterviewService(kb_repo, question_repo, AsyncMock())
        with pytest.raises(BusinessException) as raised:
            await service.create_session(object(), CreateKnowledgeBaseInterviewRequest(
                knowledgeBaseId=1, difficulty="mid", mainQuestionCount=1, followUpCount=2
            ))
        assert raised.value.code == ErrorCode.INTERVIEW_QUESTION_INSUFFICIENT

    asyncio.run(scenario())

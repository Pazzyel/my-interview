import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from common.exceptions import BusinessException
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from modules.knowledgebase.model.knowledgebase_question import (
    KnowledgeBaseQuestionEntity,
    GeneratedQuestion,
    GeneratedQuestionList,
    KnowledgeBaseQuestionFollowUpDTO,
    QuestionGenStatus,
    QuestionGenerationConfig,
)
from modules.knowledgebase.service.question_generation_state_service import QuestionGenerationStateService
from modules.knowledgebase.service.knowledgebase_question_generation_service import (
    KnowledgeBaseQuestionGenerationService,
)


def test_generation_state_rejects_duplicate_and_ignores_stale_result() -> None:
    async def scenario() -> None:
        kb_repo = AsyncMock()
        question_repo = AsyncMock()
        service = QuestionGenerationStateService(kb_repo, question_repo)
        processing = KnowledgeBaseEntity(
            id=1, vector_status=VectorStatus.COMPLETED,
            question_gen_status=QuestionGenStatus.PROCESSING, question_gen_task_id="current",
        )
        kb_repo.find_by_id_for_update.return_value = processing
        with pytest.raises(BusinessException):
            await service.create_task(
                object(), 1, QuestionGenerationConfig(
                    difficulty="mid", questionCount=5, followUpCount=2, categoryLimit=3
                )
            )
        completed = await service.replace_questions_and_complete(
            object(), 1, "old", [KnowledgeBaseQuestionEntity(
                knowledgeBaseId=1, category="Redis", question="Q"
            )], 0
        )
        assert not completed
        question_repo.replace_all.assert_not_awaited()

    asyncio.run(scenario())


def test_generation_cleaning_deduplicates_and_limits_followups() -> None:
    service = KnowledgeBaseQuestionGenerationService(
        AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    )
    kb = KnowledgeBaseEntity(id=1, name="KB", file_hash="hash")
    generated = GeneratedQuestionList(questions=[
        GeneratedQuestion(
            category=" Redis ", question="Redis 为什么快？", keyPoints=[" 单线程 ", ""],
            followUps=[
                KnowledgeBaseQuestionFollowUpDTO(question="追问 1"),
                KnowledgeBaseQuestionFollowUpDTO(question="追问 2"),
            ],
        ),
        GeneratedQuestion(category="Redis", question="redis为什么快"),
        GeneratedQuestion(category="Redis", question="   "),
    ])
    questions, skipped = service._build_entities(
        kb,
        QuestionGenerationConfig(
            difficulty="mid", questionCount=3, followUpCount=1, categoryLimit=2
        ),
        "context",
        generated,
    )
    assert len(questions) == 1
    assert skipped == 2
    assert questions[0].category == "Redis"
    assert questions[0].key_points == ["单线程"]
    assert [item.question for item in questions[0].follow_ups] == ["追问 1"]


def test_stale_processing_task_is_reset_for_recovery() -> None:
    async def scenario() -> None:
        kb_repo = AsyncMock()
        service = QuestionGenerationStateService(kb_repo, AsyncMock())
        updated_at = datetime.now() - timedelta(minutes=30)
        kb_repo.find_by_id_for_update.return_value = KnowledgeBaseEntity(
            id=1,
            question_gen_status=QuestionGenStatus.PROCESSING,
            question_gen_task_id="task",
            question_gen_updated_at=updated_at,
        )
        changed = await service.recover_if_stale(
            object(), 1, "task", QuestionGenStatus.PROCESSING, datetime.now() - timedelta(minutes=20)
        )
        assert changed
        values = kb_repo.update_question_generation_state.await_args.kwargs
        assert values["question_gen_status"] == QuestionGenStatus.QUEUED

    asyncio.run(scenario())


def test_generation_state_atomically_replaces_current_task() -> None:
    async def scenario() -> None:
        kb_repo = AsyncMock()
        question_repo = AsyncMock()
        service = QuestionGenerationStateService(kb_repo, question_repo)
        kb_repo.find_by_id_for_update.return_value = KnowledgeBaseEntity(
            id=1, vector_status=VectorStatus.COMPLETED,
            question_gen_status=QuestionGenStatus.PROCESSING, question_gen_task_id="task",
        )
        questions = [KnowledgeBaseQuestionEntity(knowledgeBaseId=1, category="Redis", question="Q")]
        assert await service.replace_questions_and_complete(object(), 1, "task", questions, 2)
        question_repo.replace_all.assert_awaited_once()
        values = kb_repo.update_question_generation_state.await_args.kwargs
        assert values["question_gen_status"] == QuestionGenStatus.COMPLETED
        assert values["question_gen_saved_count"] == 1
        assert values["question_gen_skipped_count"] == 2

    asyncio.run(scenario())

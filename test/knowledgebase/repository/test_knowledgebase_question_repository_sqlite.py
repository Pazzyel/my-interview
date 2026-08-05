import asyncio
from datetime import datetime

from knowledgebase_repository_mocks import InMemorySqliteSessionFactory, build_knowledgebase_entity
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.model.knowledgebase_question import (
    KnowledgeBaseQuestionEntity,
    KnowledgeBaseQuestionFollowUpDTO,
    KnowledgeBaseQuestionStatus,
)
from modules.knowledgebase.repository.knowledgebase_question_repository import (
    KnowledgeBaseQuestionRepository,
)
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository


def test_question_crud_filters_categories_and_legacy_followups() -> None:
    async def scenario() -> None:
        factory = InMemorySqliteSessionFactory()
        await factory.init()
        try:
            kb_repo = KnowledgeBaseRepository()
            question_repo = KnowledgeBaseQuestionRepository()
            async with factory.session() as db:
                kb = build_knowledgebase_entity(
                    file_hash="question-repo", vector_status=VectorStatus.COMPLETED,
                    uploaded_at=datetime(2026, 8, 5, 10, 0, 0),
                )
                await kb_repo.save(db, kb)
                first = KnowledgeBaseQuestionEntity(
                    knowledge_base_id=kb.id, category="Redis", difficulty="mid",
                    question="Redis 为什么快？", status=KnowledgeBaseQuestionStatus.ACTIVE,
                    follow_ups=[KnowledgeBaseQuestionFollowUpDTO(question="单线程有什么优势？")],
                )
                second = KnowledgeBaseQuestionEntity(
                    knowledge_base_id=kb.id, category="MySQL", difficulty="senior",
                    question="解释 MVCC", status=KnowledgeBaseQuestionStatus.DRAFT,
                )
                await question_repo.save(db, first)
                await question_repo.save(db, second)
                await db.commit()

                active = await question_repo.list_questions(
                    db, kb.id, status=KnowledgeBaseQuestionStatus.ACTIVE, category="Redis"
                )
                assert [item.question for item in active] == ["Redis 为什么快？"]
                assert active[0].follow_ups[0].question == "单线程有什么优势？"
                categories = await question_repo.list_categories(db, kb.id)
                assert [(item.category, item.count) for item in categories] == [("MySQL", 1), ("Redis", 1)]

                first.question = "Redis 的线程模型是什么？"
                await question_repo.save(db, first)
                await db.commit()
                assert (await question_repo.find_by_id(db, first.id)).question == "Redis 的线程模型是什么？"
                assert await question_repo.delete_by_id(db, second.id)
                await db.commit()
        finally:
            await factory.dispose()

    asyncio.run(scenario())

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from infrastructure.database.models import KnowledgeBaseORM, KnowledgeBaseQuestionORM
from modules.knowledgebase.model.knowledgebase_question import (
    CategoryCount,
    KnowledgeBaseQuestionEntity,
    KnowledgeBaseQuestionFollowUpDTO,
    KnowledgeBaseQuestionStatus,
)


def _clean_list(values: list[str] | None) -> list[str]:
    return [str(item).strip() for item in (values or []) if item and str(item).strip()]


def _read_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _read_follow_ups(raw: str | None) -> list[KnowledgeBaseQuestionFollowUpDTO]:
    result: list[KnowledgeBaseQuestionFollowUpDTO] = []
    for item in _read_json_list(raw):
        if isinstance(item, str):
            if item.strip():
                result.append(KnowledgeBaseQuestionFollowUpDTO(question=item.strip()))
            continue
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        result.append(KnowledgeBaseQuestionFollowUpDTO.model_validate({
            "question": question,
            "referenceAnswer": item.get("referenceAnswer", item.get("reference_answer")),
            "keyPoints": item.get("keyPoints", item.get("key_points", [])) or [],
            "scoringRubric": item.get("scoringRubric", item.get("scoring_rubric")),
        }))
    return result


def _to_entity(orm: KnowledgeBaseQuestionORM) -> KnowledgeBaseQuestionEntity:
    kb = getattr(orm, "knowledge_base", None)
    return KnowledgeBaseQuestionEntity(
        id=orm.id,
        knowledge_base_id=orm.knowledge_base_id,
        knowledge_base_name=kb.name if kb is not None else None,
        skill_id=orm.skill_id,
        difficulty=orm.difficulty,
        type=orm.type,
        category=orm.category,
        question=orm.question,
        topic_summary=orm.topic_summary,
        reference_answer=orm.reference_answer,
        key_points=_clean_list(_read_json_list(orm.key_points_json)),
        scoring_rubric=orm.scoring_rubric,
        follow_ups=_read_follow_ups(orm.follow_ups_json),
        source_context=orm.source_context,
        kb_content_hash=orm.kb_content_hash,
        status=orm.status,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def _to_values(entity: KnowledgeBaseQuestionEntity) -> dict[str, Any]:
    return {
        "knowledge_base_id": entity.knowledge_base_id,
        "skill_id": entity.skill_id,
        "difficulty": entity.difficulty,
        "type": entity.type,
        "category": entity.category,
        "question": entity.question,
        "topic_summary": entity.topic_summary,
        "reference_answer": entity.reference_answer,
        "key_points_json": json.dumps(_clean_list(entity.key_points), ensure_ascii=False),
        "scoring_rubric": entity.scoring_rubric,
        "follow_ups_json": json.dumps(
            [item.model_dump(by_alias=True) for item in entity.follow_ups], ensure_ascii=False
        ),
        "source_context": entity.source_context,
        "kb_content_hash": entity.kb_content_hash,
        "status": entity.status,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


class KnowledgeBaseQuestionRepository:
    async def find_by_id(
        self, db: AsyncSession, question_id: int
    ) -> KnowledgeBaseQuestionEntity | None:
        result = await db.execute(
            select(KnowledgeBaseQuestionORM)
            .options(joinedload(KnowledgeBaseQuestionORM.knowledge_base))
            .where(KnowledgeBaseQuestionORM.id == question_id)
        )
        orm = result.scalar_one_or_none()
        return _to_entity(orm) if orm else None

    async def list_questions(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        status: KnowledgeBaseQuestionStatus | None = None,
        category: str | None = None,
        difficulty: str | None = None,
        keyword: str | None = None,
    ) -> list[KnowledgeBaseQuestionEntity]:
        stmt = (
            select(KnowledgeBaseQuestionORM)
            .options(joinedload(KnowledgeBaseQuestionORM.knowledge_base))
            .where(KnowledgeBaseQuestionORM.knowledge_base_id == knowledge_base_id)
            .order_by(desc(KnowledgeBaseQuestionORM.updated_at))
        )
        if status is not None:
            stmt = stmt.where(KnowledgeBaseQuestionORM.status == status)
        if category and category.strip():
            stmt = stmt.where(KnowledgeBaseQuestionORM.category == category.strip())
        if difficulty and difficulty.strip():
            stmt = stmt.where(KnowledgeBaseQuestionORM.difficulty == difficulty.strip())
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.where(
                KnowledgeBaseQuestionORM.question.ilike(pattern)
                | KnowledgeBaseQuestionORM.topic_summary.ilike(pattern)
                | KnowledgeBaseQuestionORM.reference_answer.ilike(pattern)
            )
        result = await db.execute(stmt)
        return [_to_entity(item) for item in result.scalars().all()]

    async def list_categories(self, db: AsyncSession, knowledge_base_id: int) -> list[CategoryCount]:
        result = await db.execute(
            select(KnowledgeBaseQuestionORM.category, func.count(KnowledgeBaseQuestionORM.id))
            .where(
                KnowledgeBaseQuestionORM.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseQuestionORM.category.is_not(None),
                KnowledgeBaseQuestionORM.category != "",
            )
            .group_by(KnowledgeBaseQuestionORM.category)
            .order_by(func.count(KnowledgeBaseQuestionORM.id).desc(), KnowledgeBaseQuestionORM.category)
        )
        return [
            CategoryCount(category=category, count=count) for category, count in result.all()
        ]

    async def list_active(
        self, db: AsyncSession, knowledge_base_id: int, difficulty: str, category: str | None = None
    ) -> list[KnowledgeBaseQuestionEntity]:
        return await self.list_questions(
            db, knowledge_base_id, KnowledgeBaseQuestionStatus.ACTIVE, category, difficulty
        )

    async def list_recent_questions(
        self, db: AsyncSession, knowledge_base_id: int, difficulty: str, limit: int = 20
    ) -> list[str]:
        result = await db.execute(
            select(KnowledgeBaseQuestionORM.question)
            .where(
                KnowledgeBaseQuestionORM.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseQuestionORM.difficulty == difficulty,
            )
            .order_by(desc(KnowledgeBaseQuestionORM.updated_at))
            .limit(limit)
        )
        return [item.strip() for item in result.scalars().all() if item and item.strip()]

    async def save(
        self, db: AsyncSession, entity: KnowledgeBaseQuestionEntity
    ) -> KnowledgeBaseQuestionEntity:
        if entity.id is None:
            orm = KnowledgeBaseQuestionORM(**_to_values(entity))
            db.add(orm)
            await db.flush()
            entity.id = orm.id
            return entity
        orm = await db.get(KnowledgeBaseQuestionORM, entity.id)
        if orm is None:
            return entity
        for key, value in _to_values(entity).items():
            setattr(orm, key, value)
        await db.flush()
        return entity

    async def delete_by_id(self, db: AsyncSession, question_id: int) -> bool:
        result = await db.execute(
            delete(KnowledgeBaseQuestionORM).where(KnowledgeBaseQuestionORM.id == question_id)
        )
        return bool(result.rowcount)

    async def replace_all(
        self, db: AsyncSession, knowledge_base_id: int, questions: list[KnowledgeBaseQuestionEntity]
    ) -> None:
        await db.execute(
            delete(KnowledgeBaseQuestionORM).where(
                KnowledgeBaseQuestionORM.knowledge_base_id == knowledge_base_id
            )
        )
        for question in questions:
            db.add(KnowledgeBaseQuestionORM(**_to_values(question)))
        await db.flush()

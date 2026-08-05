import json
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.model.knowledgebase_question import (
    KnowledgeBaseQuestionEntity,
    QuestionGenStatus,
    QuestionGenStatusResponse,
    QuestionGenerationConfig,
)
from modules.knowledgebase.repository.knowledgebase_question_repository import (
    KnowledgeBaseQuestionRepository,
)
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository


class QuestionGenerationStateService:
    SAFE_FAILURE_MESSAGE = "题目生成失败，请稍后重试"

    def __init__(
        self,
        knowledgebase_repository: KnowledgeBaseRepository,
        question_repository: KnowledgeBaseQuestionRepository,
    ) -> None:
        self.knowledgebase_repository = knowledgebase_repository
        self.question_repository = question_repository

    async def create_task(
        self, db: AsyncSession, knowledge_base_id: int, config: QuestionGenerationConfig
    ) -> QuestionGenStatusResponse:
        kb = await self.knowledgebase_repository.find_by_id_for_update(db, knowledge_base_id)
        if kb is None:
            raise BusinessException(ErrorCode.KB_NOT_FOUND, "知识库不存在")
        if kb.vector_status != VectorStatus.COMPLETED:
            raise BusinessException(ErrorCode.BAD_REQUEST, "知识库尚未完成向量化")
        if kb.question_gen_status in {QuestionGenStatus.QUEUED, QuestionGenStatus.PROCESSING}:
            raise BusinessException(ErrorCode.BAD_REQUEST, "知识库题目正在生成中，请勿重复提交")
        task_id = str(uuid.uuid4())
        now = datetime.now()
        await self.knowledgebase_repository.update_question_generation_state(
            db,
            knowledge_base_id,
            question_gen_task_id=task_id,
            question_gen_status=QuestionGenStatus.QUEUED,
            question_gen_config=config.model_dump_json(by_alias=True),
            question_gen_error=None,
            question_gen_message=None,
            question_gen_saved_count=0,
            question_gen_skipped_count=0,
            question_gen_updated_at=now,
        )
        return QuestionGenStatusResponse(
            knowledge_base_id=knowledge_base_id,
            question_gen_status=QuestionGenStatus.QUEUED,
            question_gen_task_id=task_id,
            question_gen_config=config,
            updated_at=now,
        )

    async def get_status(
        self, db: AsyncSession, knowledge_base_id: int
    ) -> QuestionGenStatusResponse:
        kb = await self.knowledgebase_repository.find_by_id(db, knowledge_base_id)
        if kb is None:
            raise BusinessException(ErrorCode.KB_NOT_FOUND, "知识库不存在")
        config = None
        if kb.question_gen_config:
            try:
                config = QuestionGenerationConfig.model_validate(json.loads(kb.question_gen_config))
            except (json.JSONDecodeError, ValueError) as error:
                raise BusinessException(ErrorCode.INTERNAL_ERROR, "解析题目生成配置失败") from error
        return QuestionGenStatusResponse(
            knowledge_base_id=knowledge_base_id,
            question_gen_status=kb.question_gen_status,
            question_gen_task_id=kb.question_gen_task_id,
            question_gen_config=config,
            saved_count=kb.question_gen_saved_count,
            skipped_count=kb.question_gen_skipped_count,
            message=kb.question_gen_message,
            error=kb.question_gen_error,
            updated_at=kb.question_gen_updated_at,
        )

    async def get_config(
        self, db: AsyncSession, knowledge_base_id: int, task_id: str
    ) -> QuestionGenerationConfig:
        status = await self.get_status(db, knowledge_base_id)
        if status.question_gen_task_id != task_id:
            raise BusinessException(ErrorCode.BAD_REQUEST, "题目生成任务已失效")
        if status.question_gen_config is None:
            raise BusinessException(ErrorCode.INTERNAL_ERROR, "题目生成配置不存在")
        return status.question_gen_config

    async def try_mark_processing(
        self, db: AsyncSession, knowledge_base_id: int, task_id: str
    ) -> bool:
        return await self._transition(
            db, knowledge_base_id, task_id, QuestionGenStatus.QUEUED, QuestionGenStatus.PROCESSING
        )

    async def reset_for_retry(
        self, db: AsyncSession, knowledge_base_id: int, task_id: str
    ) -> bool:
        return await self._transition(
            db, knowledge_base_id, task_id, QuestionGenStatus.PROCESSING, QuestionGenStatus.QUEUED
        )

    async def mark_failed(self, db: AsyncSession, knowledge_base_id: int, task_id: str) -> bool:
        kb = await self.knowledgebase_repository.find_by_id_for_update(db, knowledge_base_id)
        if kb is None or kb.question_gen_task_id != task_id:
            return False
        if kb.question_gen_status == QuestionGenStatus.COMPLETED:
            return False
        await self.knowledgebase_repository.update_question_generation_state(
            db,
            knowledge_base_id,
            question_gen_status=QuestionGenStatus.FAILED,
            question_gen_error=self.SAFE_FAILURE_MESSAGE,
            question_gen_updated_at=datetime.now(),
        )
        return True

    async def replace_questions_and_complete(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        task_id: str,
        questions: list[KnowledgeBaseQuestionEntity],
        skipped_count: int,
    ) -> bool:
        kb = await self.knowledgebase_repository.find_by_id_for_update(db, knowledge_base_id)
        if (
            kb is None
            or kb.question_gen_task_id != task_id
            or kb.question_gen_status != QuestionGenStatus.PROCESSING
        ):
            return False
        await self.question_repository.replace_all(db, knowledge_base_id, questions)
        saved_count = len(questions)
        message = f"已生成 {saved_count} 道题"
        if skipped_count:
            message += f"，跳过 {skipped_count} 道无效或重复题"
        await self.knowledgebase_repository.update_question_generation_state(
            db,
            knowledge_base_id,
            question_gen_status=QuestionGenStatus.COMPLETED,
            question_gen_error=None,
            question_gen_message=message,
            question_gen_saved_count=saved_count,
            question_gen_skipped_count=skipped_count,
            question_gen_updated_at=datetime.now(),
        )
        return True

    async def recover_if_stale(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        task_id: str,
        expected: QuestionGenStatus,
        threshold: datetime,
    ) -> bool:
        kb = await self.knowledgebase_repository.find_by_id_for_update(db, knowledge_base_id)
        if (
            kb is None
            or kb.question_gen_task_id != task_id
            or kb.question_gen_status != expected
            or (kb.question_gen_updated_at is not None and kb.question_gen_updated_at >= threshold)
        ):
            return False
        values: dict[str, object] = {"question_gen_updated_at": datetime.now()}
        if expected == QuestionGenStatus.PROCESSING:
            values["question_gen_status"] = QuestionGenStatus.QUEUED
        await self.knowledgebase_repository.update_question_generation_state(
            db, knowledge_base_id, **values
        )
        return True

    async def _transition(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        task_id: str,
        expected: QuestionGenStatus,
        target: QuestionGenStatus,
    ) -> bool:
        kb = await self.knowledgebase_repository.find_by_id_for_update(db, knowledge_base_id)
        if (
            kb is None
            or kb.question_gen_task_id != task_id
            or kb.question_gen_status != expected
        ):
            return False
        await self.knowledgebase_repository.update_question_generation_state(
            db,
            knowledge_base_id,
            question_gen_status=target,
            question_gen_error=None,
            question_gen_updated_at=datetime.now(),
        )
        return True

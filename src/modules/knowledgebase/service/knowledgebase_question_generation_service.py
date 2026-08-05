import logging
import unicodedata

from common.exceptions import BusinessException, ErrorCode
from common.llm_provider import LlmProviderResolver
from common.prompt_security import DATA_BOUNDARY_INSTRUCTION, sanitize_prompt_data, wrap_prompt_data
from infrastructure.database.connection import async_session_factory
from infrastructure.prompt.prompt_service import load_prompt
from modules.knowledgebase.model.knowledgebase_question import (
    GeneratedQuestionList,
    KnowledgeBaseQuestionEntity,
    KnowledgeBaseQuestionFollowUpDTO,
    KnowledgeBaseQuestionStatus,
    QuestionGenerationConfig,
)
from modules.knowledgebase.repository.knowledgebase_question_repository import (
    KnowledgeBaseQuestionRepository,
)
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService
from modules.knowledgebase.service.question_generation_state_service import (
    QuestionGenerationStateService,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseQuestionGenerationService:
    RETRIEVAL_TOP_K = 12
    RETRIEVAL_QUERY_TOP_K = 4
    MAX_CONTEXT_CHARS = 5000

    def __init__(
        self,
        knowledgebase_repository: KnowledgeBaseRepository,
        question_repository: KnowledgeBaseQuestionRepository,
        vector_service: KnowledgeBaseVectorService,
        llm_provider_resolver: LlmProviderResolver,
        state_service: QuestionGenerationStateService,
    ) -> None:
        self.knowledgebase_repository = knowledgebase_repository
        self.question_repository = question_repository
        self.vector_service = vector_service
        self.llm_provider_resolver = llm_provider_resolver
        self.state_service = state_service

    async def execute_generation(
        self, knowledge_base_id: int, task_id: str, config: QuestionGenerationConfig
    ) -> None:
        async with async_session_factory() as db:
            kb = await self.knowledgebase_repository.find_by_id(db, knowledge_base_id)
            if kb is None:
                raise BusinessException(ErrorCode.KB_NOT_FOUND, "知识库不存在")
            if kb.question_gen_task_id != task_id:
                logger.info("Discard stale question generation task: kbId=%s", knowledge_base_id)
                return
            categories = await self.question_repository.list_categories(db, knowledge_base_id)
            existing = await self.question_repository.list_recent_questions(
                db, knowledge_base_id, config.difficulty
            )

        context = await self._build_context(knowledge_base_id)
        prompt = await load_prompt("knowledgebase-question-generation")
        model = await self.llm_provider_resolver.resolve(config.llm_provider)
        chain = prompt | model.with_structured_output(GeneratedQuestionList)
        try:
            generated = await chain.ainvoke({
                "knowledgeBaseName": sanitize_prompt_data(kb.name),
                "difficulty": config.difficulty,
                "questionCount": config.question_count,
                "followUpCount": config.follow_up_count,
                "categoryLimit": config.category_limit,
                "existingCategories": sanitize_prompt_data(
                    "\n".join(f"- {item.category}（{item.count} 题）" for item in categories)
                    or "暂无已有方向"
                ),
                "existingQuestions": sanitize_prompt_data(
                    "\n".join(f"- {item}" for item in existing) or "暂无已有题目"
                ),
                "context": DATA_BOUNDARY_INSTRUCTION + "\n" + wrap_prompt_data(
                    "knowledge-base", sanitize_prompt_data(context)
                ),
            })
        except Exception as error:
            logger.error("Knowledgebase question LLM generation failed: kbId=%s", knowledge_base_id, exc_info=True)
            raise BusinessException(
                ErrorCode.INTERVIEW_QUESTION_GENERATION_FAILED, f"知识库题库生成失败：{error}"
            ) from error
        if not isinstance(generated, GeneratedQuestionList):
            generated = GeneratedQuestionList.model_validate(generated)
        questions, skipped = self._build_entities(kb, config, context, generated)
        if not questions:
            raise BusinessException(ErrorCode.INTERVIEW_QUESTION_GENERATION_FAILED, "题库生成结果无有效题干")
        async with async_session_factory() as db:
            try:
                completed = await self.state_service.replace_questions_and_complete(
                    db, knowledge_base_id, task_id, questions, skipped
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        if not completed:
            logger.info("Discard generated result for replaced task: kbId=%s", knowledge_base_id)

    async def _build_context(self, knowledge_base_id: int) -> str:
        queries = [
            "核心概念 定义 背景 原理",
            "关键流程 步骤 方法 工作机制",
            "规则约束 条件 边界 例外 限制",
            "典型案例 常见问题 应用场景 最佳实践",
        ]
        texts: list[str] = []
        seen: set[str] = set()
        for query in queries:
            docs = await self.vector_service.similar_search(
                query=query,
                knowledgebase_ids=[knowledge_base_id],
                top_k=self.RETRIEVAL_QUERY_TOP_K,
                min_score=0,
            )
            for doc in docs:
                value = (doc.page_content or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    texts.append(value)
                if len(texts) >= self.RETRIEVAL_TOP_K:
                    break
            if len(texts) >= self.RETRIEVAL_TOP_K:
                break
        if not texts:
            raise BusinessException(ErrorCode.AI_SERVICE_ERROR, "知识库未检索到可用于生成题目的内容")
        context = "\n\n---\n\n".join(texts)
        return context[: self.MAX_CONTEXT_CHARS]

    def _build_entities(self, kb, config, context, generated):
        entities: list[KnowledgeBaseQuestionEntity] = []
        seen: set[str] = set()
        skipped = 0
        for item in generated.questions:
            question = (item.question or "").strip()
            key = self._question_key(question)
            if not question or not key or key in seen:
                skipped += 1
                continue
            seen.add(key)
            follow_ups = []
            for follow_up in item.follow_ups:
                text = (follow_up.question or "").strip()
                if not text:
                    continue
                follow_ups.append(KnowledgeBaseQuestionFollowUpDTO(
                    question=text,
                    reference_answer=self._trim(follow_up.reference_answer),
                    key_points=self._clean_strings(follow_up.key_points),
                    scoring_rubric=self._trim(follow_up.scoring_rubric),
                ))
                if len(follow_ups) >= config.follow_up_count:
                    break
            entities.append(KnowledgeBaseQuestionEntity(
                knowledge_base_id=kb.id,
                knowledge_base_name=kb.name,
                difficulty=config.difficulty,
                type=self._trim(item.type),
                category=self._trim(item.category) or kb.name or "未分类",
                question=question,
                topic_summary=self._trim(item.topic_summary),
                reference_answer=self._trim(item.reference_answer),
                key_points=self._clean_strings(item.key_points),
                scoring_rubric=self._trim(item.scoring_rubric),
                follow_ups=follow_ups,
                source_context=context,
                kb_content_hash=kb.file_hash,
                status=KnowledgeBaseQuestionStatus.DRAFT,
            ))
        return entities, skipped

    @staticmethod
    def _question_key(value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).lower()
        return "".join(char for char in normalized if char.isalnum())

    @staticmethod
    def _trim(value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @staticmethod
    def _clean_strings(values: list[str]) -> list[str]:
        return [item.strip() for item in values if item and item.strip()]

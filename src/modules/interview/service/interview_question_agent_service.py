import asyncio
import logging
from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import add_messages
from langgraph.types import Checkpointer, Command
from pydantic import BaseModel, Field

from common.exceptions import BusinessException, ErrorCode
from common.llm_provider import LlmProviderRegistry, LlmProviderResolver
from common.prompt_security import sanitize_prompt_data, wrap_prompt_data
from infrastructure.prompt.prompt_service import has_short_memory, load_prompt
from modules.interview.model.interview_agent_dto import Difficulty, HistoricalQuestion, InterviewQuestionDTO
from modules.interview.model.interview_agent_llm_models import InterviewQuestionLLMItem, InterviewQuestionLLMOutput
from modules.interview.model.interview_skill_dto import CategoryDTO, SkillDTO
from modules.interview.service.interview_skill_service import InterviewSkillService

logger = logging.getLogger(__name__)


class InterviewQuestionGraphState(BaseModel):
    resume_text: str = ""
    question_count: int = 6
    historical_questions: list[HistoricalQuestion] = Field(default_factory=list)
    skill_id: str = "java-backend"
    difficulty: Difficulty = Difficulty.MID
    custom_categories: list[CategoryDTO] | None = None
    jd_text: str | None = None
    llm_provider: str | None = None
    messages: Annotated[list[AnyMessage], add_messages] = []
    generated: list[InterviewQuestionLLMItem] = Field(default_factory=list)
    questions: list[InterviewQuestionDTO] = Field(default_factory=list)
    error_message: str | None = None


class InterviewQuestionAgentService:
    FOLLOW_UP_COUNT = 1
    RESUME_RATIO = 0.6

    def __init__(
        self,
        skill_service: InterviewSkillService | None = None,
        llm_provider_resolver: LlmProviderResolver | None = None,
    ) -> None:
        self.skill_service = skill_service or InterviewSkillService()
        self.llm_provider_resolver = llm_provider_resolver or LlmProviderRegistry()
        self._graph_ready = False
        self._chat_model: Any | None = None  # compatibility injection point for unit tests

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        _ = checkpointer
        self._graph_ready = True

    async def generate_questions(
        self,
        resume_text: str,
        question_count: int,
        historical_questions: list[HistoricalQuestion] | list[str],
        session_id: str,
        skill_id: str = "java-backend",
        difficulty: Difficulty = Difficulty.MID,
        custom_categories: list[CategoryDTO] | None = None,
        jd_text: str | None = None,
        llm_provider: str | None = None,
    ) -> list[InterviewQuestionDTO]:
        if question_count <= 0:
            raise BusinessException(ErrorCode.BAD_REQUEST, "题目数量必须大于 0")
        history = [
            item if isinstance(item, HistoricalQuestion) else HistoricalQuestion(question=item, type="GENERAL")
            for item in historical_questions
        ]
        state = InterviewQuestionGraphState(
            resume_text=resume_text,
            question_count=question_count,
            historical_questions=history,
            skill_id=skill_id,
            difficulty=difficulty,
            custom_categories=custom_categories,
            jd_text=jd_text,
            llm_provider=llm_provider,
        )
        config: RunnableConfig = {"configurable": {"thread_id": f"interview-question-{session_id}"}}
        generated: list[InterviewQuestionLLMItem] = []
        try:
            skill = self._resolve_skill(state)
            if resume_text.strip():
                resume_count = max(1, round(question_count * self.RESUME_RATIO))
                skill_count = max(0, question_count - resume_count)
                tasks = [self._invoke_resume_generation(state, resume_count, config)]
                if skill_count:
                    tasks.append(self._invoke_skill_generation(state, skill, skill_count, config))
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, InterviewQuestionLLMOutput):
                        generated.extend(result.questions)
                    elif isinstance(result, Exception):
                        logger.warning("部分面试题生成失败: %s", result)
            else:
                generated.extend((await self._invoke_skill_generation(state, skill, question_count, config)).questions)
            return self._normalize(generated, question_count, skill)
        except Exception as error:
            logger.error("面试题生成失败，使用兜底题目: %s", error, exc_info=True)
            return self._build_fallback_questions(question_count, self._resolve_skill(state))

    async def _invoke_skill_generation(
        self, state: InterviewQuestionGraphState, skill: SkillDTO, count: int, config: RunnableConfig
    ) -> InterviewQuestionLLMOutput:
        allocation = self.skill_service.calculate_allocation(skill.categories, count)
        prompt = await load_prompt("interview-question-skill", has_short_memory(config))
        chain = prompt | (await self._model(state.llm_provider)).with_structured_output(InterviewQuestionLLMOutput)
        result = await chain.ainvoke({
            "persona": skill.persona or "你是一名严谨的技术面试官。",
            "skillName": skill.name,
            "skillDescription": skill.description,
            "difficulty": self._difficulty_description(state.difficulty),
            "questionCount": count,
            "followUpCount": self.FOLLOW_UP_COUNT,
            "allocation": self.skill_service.build_allocation_description(allocation, skill.categories),
            "references": self.skill_service.build_reference_section(skill, allocation),
            "jdSection": (
                wrap_prompt_data("jd", sanitize_prompt_data(skill.source_jd))
                if skill.source_jd else "未提供 JD"
            ),
            "historicalQuestions": self._history_text(state.historical_questions),
            "messages": state.messages,
        })
        return result if isinstance(result, InterviewQuestionLLMOutput) else InterviewQuestionLLMOutput.model_validate(result)

    async def _invoke_resume_generation(
        self, state: InterviewQuestionGraphState, count: int, config: RunnableConfig
    ) -> InterviewQuestionLLMOutput:
        prompt = await load_prompt("interview-question-resume", has_short_memory(config))
        chain = prompt | (await self._model(state.llm_provider)).with_structured_output(InterviewQuestionLLMOutput)
        result = await chain.ainvoke({
            "resumeText": wrap_prompt_data("resume", sanitize_prompt_data(state.resume_text)),
            "difficulty": self._difficulty_description(state.difficulty),
            "questionCount": count,
            "followUpCount": self.FOLLOW_UP_COUNT,
            "historicalQuestions": self._history_text(state.historical_questions),
            "messages": state.messages,
        })
        return result if isinstance(result, InterviewQuestionLLMOutput) else InterviewQuestionLLMOutput.model_validate(result)

    def _resolve_skill(self, state: InterviewQuestionGraphState) -> SkillDTO:
        if state.skill_id == InterviewSkillService.CUSTOM_SKILL_ID:
            if not state.custom_categories:
                raise BusinessException(ErrorCode.BAD_REQUEST, "自定义面试必须提供 customCategories")
            return self.skill_service.build_custom_skill(state.custom_categories, state.jd_text or "")
        return self.skill_service.get_skill(state.skill_id)

    def _normalize(
        self, generated: list[InterviewQuestionLLMItem], question_count: int, skill: SkillDTO
    ) -> list[InterviewQuestionDTO]:
        usable = [item for item in generated if item.question.strip()][:question_count]
        if len(usable) < question_count:
            fallback = self._fallback_items(question_count - len(usable), skill, offset=len(usable))
            usable.extend(fallback)
        result: list[InterviewQuestionDTO] = []
        for item in usable:
            main_index = len(result)
            question_type = (item.type or "GENERAL").strip().upper()
            result.append(InterviewQuestionDTO(
                question_index=main_index,
                question=item.question.strip(),
                type=question_type,
                category=(item.category or question_type).strip(),
                topic_summary=item.topic_summary,
            ))
            followups = [text.strip() for text in item.follow_ups if text and text.strip()]
            for followup in followups[: self.FOLLOW_UP_COUNT]:
                result.append(InterviewQuestionDTO(
                    question_index=len(result),
                    question=followup,
                    type=question_type,
                    category=(item.category or question_type).strip(),
                    topic_summary=item.topic_summary,
                    is_follow_up=True,
                    parent_question_index=main_index,
                ))
        return result

    def _build_fallback_questions(self, question_count: int, skill: SkillDTO | None = None) -> list[InterviewQuestionDTO]:
        skill = skill or self.skill_service.get_skill("java-backend")
        return self._normalize(self._fallback_items(question_count, skill), question_count, skill)

    @staticmethod
    def _fallback_items(count: int, skill: SkillDTO, offset: int = 0) -> list[InterviewQuestionLLMItem]:
        categories = skill.categories or []
        if not categories:
            return [InterviewQuestionLLMItem(
                question=f"请结合实际项目说明你对该技术方向核心能力的理解（{i + 1}）。",
                type="GENERAL", category="综合能力", topic_summary="综合能力",
                follow_ups=["你会如何验证该方案在生产环境中的可靠性？"],
            ) for i in range(count)]
        result = []
        for index in range(count):
            category = categories[(offset + index) % len(categories)]
            result.append(InterviewQuestionLLMItem(
                question=f"请说明你对{category.label}核心原理、适用场景和工程实践的理解。",
                type=category.key,
                category=category.label,
                topic_summary=category.label,
                follow_ups=[f"在{category.label}出现性能或稳定性问题时，你会如何排查？"],
            ))
        return result

    async def _node_prepare_question_context(self, state: InterviewQuestionGraphState, config: RunnableConfig) -> Command:
        _ = config
        return Command(update={"error_message": None}, goto="generate_questions") if state.question_count > 0 else Command(update={"error_message": "invalid_input"}, goto="fallback_questions")

    async def _node_generate_questions(self, state: InterviewQuestionGraphState, config: RunnableConfig) -> Command:
        try:
            output = await self._invoke_skill_generation(state, self._resolve_skill(state), state.question_count, config)
            return Command(update={"generated": output.questions, "error_message": None}, goto="normalize_questions")
        except Exception as error:
            return Command(update={"error_message": str(error)}, goto="fallback_questions")

    async def _node_normalize_questions(self, state: InterviewQuestionGraphState) -> Command:
        questions = self._normalize(state.generated, state.question_count, self._resolve_skill(state))
        return Command(update={"questions": questions, "error_message": None}, goto="__end__")

    async def _node_fallback_questions(self, state: InterviewQuestionGraphState) -> Command:
        questions = self._build_fallback_questions(max(1, state.question_count), self._resolve_skill(state))
        return Command(update={"questions": questions, "generated": []}, goto="__end__")

    async def _model(self, provider: str | None) -> Any:
        return self._chat_model or await self.llm_provider_resolver.resolve(provider)

    @staticmethod
    def _difficulty_description(difficulty: Difficulty) -> str:
        return {
            Difficulty.JUNIOR: "初级：关注基础概念、常用实践与清晰表达",
            Difficulty.MID: "中级：关注原理、边界条件、故障处理与工程权衡",
            Difficulty.SENIOR: "高级：关注架构决策、复杂场景、性能与系统性权衡",
        }[difficulty]

    @staticmethod
    def _history_text(history: list[HistoricalQuestion]) -> str:
        if not history:
            return "暂无历史提问"
        return "\n".join(
            f"- [{sanitize_prompt_data(item.type)}] {sanitize_prompt_data(item.question)}"
            for item in history
        )

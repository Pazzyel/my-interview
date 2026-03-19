import logging
import uuid
from typing import Annotated, cast

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import AnyMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, Command
from pydantic import BaseModel

from common.ai_config import ai_config
from common.exceptions import BusinessException, ErrorCode
from infrastructure.prompt.prompt_service import has_short_memory, load_prompt
from modules.interview.model.interview_agent_dto import InterviewQuestionDTO, QuestionType
from modules.interview.model.interview_agent_llm_models import (
    InterviewQuestionLLMItem,
    InterviewQuestionLLMOutput,
)
from modules.interview.model.interview_query_distribution import QuestionDistribution

logger = logging.getLogger(__name__)

MAX_FOLLOW_UP_COUNT: int = 2
DEFAULT_FOLLOW_UP_COUNT: int = 1

PROJECT_RATIO: float = 0.20
MYSQL_RATIO: float = 0.20
REDIS_RATIO: float = 0.20
JAVA_BASIC_RATIO: float = 0.10
JAVA_COLLECTION_RATIO: float = 0.10
JAVA_CONCURRENT_RATIO: float = 0.10


class InterviewQuestionGraphState(BaseModel):
    resume_text: str # 简历文本内容
    question_count: int # 问题的数量（持久化）
    historical_questions: list[str] = [] # 历史问题
    messages: Annotated[list[AnyMessage], add_messages] = []
    generated: list[InterviewQuestionLLMItem] = []
    questions: list[InterviewQuestionDTO] = []
    error_message: str | None = None

class InterviewQuestionAgentService:
    def __init__(self) -> None:
        self._graph: CompiledStateGraph | None = None
        self._follow_up_count: int = min(max(DEFAULT_FOLLOW_UP_COUNT, 0), MAX_FOLLOW_UP_COUNT)
        self._chat_model: ChatOpenAI = ChatOpenAI(
            model=ai_config.chat_model_name,
            api_key=ai_config.chat_api_key,
            base_url=ai_config.base_url,
            temperature=0,
        )

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        self._graph = await self._build_workflow(checkpointer)

    async def generate_questions(
        self,
        resume_text: str,
        question_count: int,
        historical_questions: list[str],
        session_id: str
    ) -> list[InterviewQuestionDTO]:
        """问题生成节点，生成面试问题"""
        if self._graph is None:
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "面试问题图尚未初始化")
        state: InterviewQuestionGraphState = InterviewQuestionGraphState(
            resume_text=resume_text,
            question_count=question_count,
            historical_questions=historical_questions,
        )
        config: RunnableConfig = {
            "configurable": {"thread_id": f"interview-question-{session_id}"}
        }
        result_state: InterviewQuestionGraphState = await self._graph.ainvoke(state, config=config)
        return result_state.questions

    async def _build_workflow(self, checkpointer: Checkpointer) -> CompiledStateGraph:
        workflow = StateGraph(InterviewQuestionGraphState)
        workflow.add_node("prepare_question_context", self._node_prepare_question_context)
        workflow.add_node("generate_questions", self._node_generate_questions)
        workflow.add_node("normalize_questions", self._node_normalize_questions)
        workflow.add_node("fallback_questions", self._node_fallback_questions)

        workflow.add_edge(START, "prepare_question_context")
        workflow.add_edge("prepare_question_context", "generate_questions")
        workflow.add_edge("prepare_question_context", "fallback_questions")
        workflow.add_edge("generate_questions", "normalize_questions")
        workflow.add_edge("generate_questions", "fallback_questions")
        workflow.add_edge("normalize_questions", END)
        workflow.add_edge("fallback_questions", END)
        return workflow.compile(checkpointer=checkpointer)

    async def _node_prepare_question_context(
        self,
        state: InterviewQuestionGraphState,
        config: RunnableConfig,
    ) -> Command:
        """
        校验出题输入是否可用，决定进入正常出题节点或兜底节点。

        Validate question-generation input and route to normal generation
        or fallback question node.
        """
        _ = config
        if state.resume_text.strip() == "" or state.question_count <= 0:
            return Command(
                update={"error_message": "invalid_input"},
                goto="fallback_questions",
            )
        return Command(
            update={"error_message": None},
            goto="generate_questions",
        )

    async def _node_generate_questions(
        self,
        state: InterviewQuestionGraphState,
        config: RunnableConfig,
    ) -> Command:
        """
        调用 LLM 生成结构化主问题与追问列表，并写入中间状态

        Invoke LLM to generate structured main questions and follow-ups,
        then store raw generated items in graph state.
        """
        prompt_template: ChatPromptTemplate = await load_prompt(
            "interview-question-generate", has_short_memory(config)
        )
        history_text: str = (
            "\n".join(state.historical_questions)
            if len(state.historical_questions) > 0
            else "暂无历史提问"
        )
        distribution: QuestionDistribution = self._calculate_distribution(state.question_count)
        chain = prompt_template | self._chat_model.with_structured_output(
            InterviewQuestionLLMOutput
        )
        try:
            llm_output: InterviewQuestionLLMOutput = cast(InterviewQuestionLLMOutput, await chain.ainvoke(
                {
                    "resumeText": state.resume_text,
                    "questionCount": state.question_count,
                    "projectCount": distribution.project,
                    "mysqlCount": distribution.mysql,
                    "redisCount": distribution.redis,
                    "javaBasicCount": distribution.java_basic,
                    "javaCollectionCount": distribution.java_collection,
                    "javaConcurrentCount": distribution.java_concurrent,
                    "springCount": distribution.spring,
                    "followUpCount": self._follow_up_count,
                    "historicalQuestions": history_text,
                    "messages": state.messages,
                }
            )) # 因为是with_structured_output，所以确信是子类
            return Command(
                update={
                    "generated": llm_output.questions,
                    "error_message": None,
                },
                goto="normalize_questions",
            )
        except Exception as error:
            logger.error("Interview question generation failed: %s", str(error), exc_info=True)
            return Command(update={"error_message": str(error)}, goto="fallback_questions")

    async def _node_normalize_questions(self, state: InterviewQuestionGraphState) -> Command:
        """
        把 LLM 输出标准化为系统题目 DTO，并展开追问形成线性题目序列。展开问题列表方便前端处理

        Normalize LLM output into internal question DTOs and flatten follow-up
        questions into a linear interview sequence.
        """
        question_list: list[InterviewQuestionDTO] = []
        question_index: int = 0
        # 本轮thread_id生成的问题都会遍历一遍
        for item in state.generated:
            if item.question.strip() == "":
                continue
            question_type: QuestionType = self._safe_question_type(item.type)
            main_index: int = question_index
            question_list.append(
                InterviewQuestionDTO(
                    question_index=question_index,
                    question=item.question.strip(),
                    type=question_type,
                    category=item.category.strip() if item.category else question_type.value,
                    user_answer=None,
                    is_follow_up=False,
                    parent_question_index=None,
                )
            )
            question_index += 1
            # 处理本问题的追问
            followups: list[str] = [
                text.strip()
                for text in item.follow_ups
                if text is not None and text.strip() != ""
            ]
            for follow_up in followups[:self._follow_up_count]:
                question_list.append(
                    InterviewQuestionDTO(
                        question_index=question_index,
                        question=follow_up,
                        type=question_type,
                        category=f"{item.category}追问",
                        user_answer=None,
                        is_follow_up=True,
                        parent_question_index=main_index,
                    )
                )
                question_index += 1
        if len(question_list) == 0:
            return Command(
                update={"error_message": "empty_questions"},
                goto="fallback_questions",
            )
        return Command(
            update={
                "questions": question_list,
                "error_message": None,
            },
            goto=END,
        )

    async def _node_fallback_questions(self, state: InterviewQuestionGraphState) -> Command:
        """
        中文：当 LLM 失败或输入无效时生成兜底题目，确保流程始终可继续。
        English: Provide fallback questions when LLM fails or input is invalid,
        ensuring interview flow remains available.
        """
        fallback_questions: list[InterviewQuestionDTO] = []
        defaults: list[tuple[str, QuestionType, str]] = [
            ("请介绍你最核心的项目以及你的职责", QuestionType.PROJECT, "项目经历"),
            ("请说明你如何设计 MySQL 索引并验证效果", QuestionType.MYSQL, "数据库"),
            ("请介绍 Redis 常见数据结构和典型使用场景", QuestionType.REDIS, "缓存"),
            ("请说明你处理并发安全问题的实践", QuestionType.JAVA_CONCURRENT, "并发"),
            ("请介绍 Spring Boot 自动配置的核心机制", QuestionType.SPRING_BOOT, "框架"),
        ]
        question_index: int = 0
        for text, question_type, category in defaults[: max(1, state.question_count)]:
            fallback_questions.append(
                InterviewQuestionDTO(
                    question_index=question_index,
                    question=text,
                    type=question_type,
                    category=category,
                    user_answer=None,
                    is_follow_up=False,
                    parent_question_index=None,
                )
            )
            question_index += 1
        return Command(
            update={
                "questions": fallback_questions,
                "generated": [],
            },
            goto=END,
        )

    def _safe_question_type(self, raw_type: str) -> QuestionType:
        try:
            return QuestionType(raw_type.upper())
        except Exception:
            return QuestionType.JAVA_BASIC

    def _calculate_distribution(self, total: int) -> QuestionDistribution:
        """
        计算各题型数量。

        Calculate per-type question counts
        """
        project: int = max(1, round(total * PROJECT_RATIO))
        mysql: int = max(1, round(total * MYSQL_RATIO))
        redis: int = max(1, round(total * REDIS_RATIO))
        java_basic: int = max(1, round(total * JAVA_BASIC_RATIO))
        java_collection: int = round(total * JAVA_COLLECTION_RATIO)
        java_concurrent: int = round(total * JAVA_CONCURRENT_RATIO)
        spring: int = total - project - mysql - redis - java_basic - java_collection - java_concurrent
        spring = max(0, spring)
        return QuestionDistribution(
            project=project,
            mysql=mysql,
            redis=redis,
            java_basic=java_basic,
            java_collection=java_collection,
            java_concurrent=java_concurrent,
            spring=spring,
        )

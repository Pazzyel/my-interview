import json
import logging
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
from modules.interview.model.interview_agent_dto import (
    InterviewQuestionDTO,
    InterviewReportDTO,
    QuestionEvaluationDTO,
    ReferenceAnswerDTO,
)
from modules.interview.model.interview_agent_llm_models import (
    InterviewEvaluationLLMOutput,
)

logger = logging.getLogger(__name__)


class InterviewEvaluateGraphState(BaseModel):
    resume_text: str
    questions: list[InterviewQuestionDTO]
    messages: Annotated[list[AnyMessage], add_messages] = []
    report: InterviewReportDTO | None = None
    error_message: str | None = None


class InterviewEvaluationAgentService:
    def __init__(self) -> None:
        self._graph: CompiledStateGraph | None = None
        self._chat_model: ChatOpenAI = ChatOpenAI(
            model=ai_config.chat_model_name,
            api_key=ai_config.chat_api_key,
            base_url=ai_config.base_url,
            temperature=0,
        )

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        self._graph = await self._build_workflow(checkpointer)

    async def evaluate(
        self,
        resume_text: str,
        questions: list[InterviewQuestionDTO],
        thread_id: str,
    ) -> InterviewReportDTO:
        """根据问题+答案列表评估本轮面试结果，用thread_id区分不同的面试"""
        if self._graph is None:
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "面试评估图尚未初始化")
        state: InterviewEvaluateGraphState = InterviewEvaluateGraphState(
            resume_text=resume_text,
            questions=questions,
        )
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        result_state: InterviewEvaluateGraphState = await self._graph.ainvoke(state, config=config)
        if result_state.report is None:
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "面试评估结果为空")
        return result_state.report

    async def _build_workflow(self, checkpointer: Checkpointer) -> CompiledStateGraph:
        workflow = StateGraph(InterviewEvaluateGraphState)
        workflow.add_node("prepare_evaluate_context", self._node_prepare_evaluate_context)
        workflow.add_node("evaluate_answers", self._node_evaluate_answers)
        workflow.add_node("fallback_report", self._node_fallback_report)

        workflow.add_edge(START, "prepare_evaluate_context")
        workflow.add_edge("prepare_evaluate_context", "evaluate_answers")
        workflow.add_edge("prepare_evaluate_context", "fallback_report")
        workflow.add_edge("evaluate_answers", END)
        workflow.add_edge("evaluate_answers", "fallback_report")
        workflow.add_edge("fallback_report", END)
        return workflow.compile(checkpointer=checkpointer)

    async def _node_prepare_evaluate_context(self, state: InterviewEvaluateGraphState) -> Command:
        """
        检查评估输入是否具备最小条件，决定进入评估节点或兜底报告节点。

        Check whether evaluation input is minimally valid and route to
        evaluation node or fallback report node.
        """
        if len(state.questions) == 0:
            return Command(
                update={"error_message": "empty_questions"},
                goto="fallback_report",
            )
        return Command(
            update={"error_message": None},
            goto="evaluate_answers",
        )

    async def _node_evaluate_answers(
        self,
        state: InterviewEvaluateGraphState,
        config: RunnableConfig,
    ) -> Command:
        """
        根据问答记录调用 LLM 生成逐题评价与总体评价。

        Invoke LLM with interview QA records to produce per-question
        evaluation and overall assessment.
        """
        prompt_template: ChatPromptTemplate = await load_prompt(
            "interview-report-evaluate", has_short_memory(config)
        )
        question_payload: list[dict[str, str | int | None]] = [
            {
                "questionIndex": item.question_index,
                "question": item.question,
                "category": item.category,
                "userAnswer": item.user_answer,
            }
            for item in state.questions
        ]
        chain = prompt_template | self._chat_model.with_structured_output(
            InterviewEvaluationLLMOutput
        )
        try:
            llm_output: InterviewEvaluationLLMOutput = cast(InterviewEvaluationLLMOutput, await chain.ainvoke(
                {
                    "resumeText": state.resume_text,
                    "qaRecords": json.dumps(question_payload, ensure_ascii=False),
                    "messages": state.messages,
                }
            )) # 强制转换
            report: InterviewReportDTO = self._build_report_from_llm(llm_output, state.questions)
            return Command(
                update={
                    "report": report,
                    "error_message": None,
                },
                goto=END,
            )
        except Exception as error:
            logger.error("Interview evaluation failed: %s", str(error), exc_info=True)
            return Command(update={"error_message": str(error)}, goto="fallback_report")

    async def _node_fallback_report(self, state: InterviewEvaluateGraphState) -> Command:
        """
        当评估失败时返回错误报告，避免主流程因模型异常中断。

        Return a error report when evaluation fails so that the
        interview flow remains resilient to model/runtime errors.
        """
        question_details: list[QuestionEvaluationDTO] = []
        reference_answers: list[ReferenceAnswerDTO] = []
        for item in state.questions:
            question_details.append(
                QuestionEvaluationDTO(
                    question_index=item.question_index,
                    question=item.question,
                    category=item.category,
                    user_answer=item.user_answer,
                    score=0,
                    feedback="未完成评估",
                )
            )
            reference_answers.append(
                ReferenceAnswerDTO(
                    question_index=item.question_index,
                    question=item.question,
                    reference_answer="暂无参考答案",
                    key_points=[],
                )
            )
        report: InterviewReportDTO = InterviewReportDTO(
            overall_score=0,
            overall_feedback="评估服务暂不可用，请稍后重试",
            strengths=[],
            improvements=["请稍后重新生成报告"],
            question_details=question_details,
            reference_answers=reference_answers,
        )
        return Command(
            update={"report": report},
            goto=END,
        )

    def _build_report_from_llm(
        self,
        llm_output: InterviewEvaluationLLMOutput,
        questions: list[InterviewQuestionDTO],
    ) -> InterviewReportDTO:
        """从LLM生成的评价结果，转换成InterviewReportDTO的形式"""
        question_map: dict[int, InterviewQuestionDTO] = {
            item.question_index: item for item in questions
        }
        details: list[QuestionEvaluationDTO] = []
        refs: list[ReferenceAnswerDTO] = []
        for eval_item in llm_output.question_evaluations:
            origin_question: InterviewQuestionDTO | None = question_map.get(eval_item.question_index)
            question_text: str = origin_question.question if origin_question is not None else "未知问题"
            category_text: str = origin_question.category if origin_question is not None else "未分类"
            user_answer_text: str | None = origin_question.user_answer if origin_question is not None else None
            details.append(
                QuestionEvaluationDTO(
                    question_index=eval_item.question_index,
                    question=question_text,
                    category=category_text,
                    user_answer=user_answer_text,
                    score=max(0, min(100, int(eval_item.score))),
                    feedback=eval_item.feedback,
                )
            )
            refs.append(
                ReferenceAnswerDTO(
                    question_index=eval_item.question_index,
                    question=question_text,
                    reference_answer=eval_item.reference_answer,
                    key_points=eval_item.key_points,
                )
            )
        return InterviewReportDTO(
            overall_score=max(0, min(100, int(llm_output.overall_score))),
            overall_feedback=llm_output.overall_feedback,
            strengths=llm_output.strengths,
            improvements=llm_output.improvements,
            question_details=details,
            reference_answers=refs,
        )

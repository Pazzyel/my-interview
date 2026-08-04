import asyncio
import json
import logging
from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import add_messages
from langgraph.types import Checkpointer, Command
from pydantic import BaseModel, Field

from common.llm_provider import LlmProviderRegistry, LlmProviderResolver
from infrastructure.prompt.prompt_service import has_short_memory, load_prompt
from modules.interview.model.interview_agent_dto import (
    CategoryScoreDTO,
    InterviewQuestionDTO,
    InterviewReportDTO,
    QuestionEvaluationDTO,
    ReferenceAnswerDTO,
)
from modules.interview.model.interview_agent_llm_models import (
    InterviewEvaluationLLMOutput,
    InterviewEvaluationSummaryLLMOutput,
)

logger = logging.getLogger(__name__)


class InterviewEvaluateGraphState(BaseModel):
    session_id: str = ""
    resume_text: str = ""
    questions: list[InterviewQuestionDTO] = Field(default_factory=list)
    llm_provider: str | None = None
    reference_context: str = ""
    messages: Annotated[list[AnyMessage], add_messages] = []
    report: InterviewReportDTO | None = None
    error_message: str | None = None


class InterviewEvaluationAgentService:
    BATCH_SIZE = 8

    def __init__(self, llm_provider_resolver: LlmProviderResolver | None = None) -> None:
        self.llm_provider_resolver = llm_provider_resolver or LlmProviderRegistry()
        self._graph_ready = False
        self._chat_model: Any | None = None

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        _ = checkpointer
        self._graph_ready = True

    async def evaluate(
        self,
        resume_text: str,
        questions: list[InterviewQuestionDTO],
        thread_id: str,
        session_id: str = "",
        llm_provider: str | None = None,
        reference_context: str = "",
    ) -> InterviewReportDTO:
        _ = thread_id
        if not questions:
            return self._fallback_report(session_id, questions)
        batches = [questions[index:index + self.BATCH_SIZE] for index in range(0, len(questions), self.BATCH_SIZE)]
        results = await asyncio.gather(*[
            self._evaluate_batch(batch, resume_text, llm_provider, reference_context)
            for batch in batches
        ], return_exceptions=True)
        outputs = [item for item in results if isinstance(item, InterviewEvaluationLLMOutput)]
        details, refs = self._merge_evaluations(outputs, questions)
        overall_score = round(sum(item.score for item in details) / len(details)) if details else 0
        category_scores = self._category_scores(details)
        summary = await self._summarize(details, overall_score, llm_provider)
        return InterviewReportDTO(
            session_id=session_id,
            total_questions=len(questions),
            overall_score=overall_score,
            category_scores=category_scores,
            overall_feedback=summary.overall_feedback,
            strengths=summary.strengths,
            improvements=summary.improvements,
            question_details=details,
            reference_answers=refs,
        )

    async def _evaluate_batch(
        self, questions: list[InterviewQuestionDTO], resume_text: str,
        provider: str | None, reference_context: str,
    ) -> InterviewEvaluationLLMOutput:
        prompt = await load_prompt("interview-report-evaluate", False)
        chain = prompt | (await self._model(provider)).with_structured_output(InterviewEvaluationLLMOutput)
        payload = [{
            "questionIndex": item.question_index,
            "question": item.question,
            "category": item.category,
            "userAnswer": item.user_answer,
            "questionReferenceAnswer": item.reference_answer,
            "questionKeyPoints": item.key_points,
            "scoringRubric": item.scoring_rubric,
        } for item in questions]
        result = await chain.ainvoke({
            "resumeText": resume_text or "未提供简历",
            "qaRecords": json.dumps(payload, ensure_ascii=False),
            "referenceContext": reference_context or "未配置 Skill references",
        })
        return result if isinstance(result, InterviewEvaluationLLMOutput) else InterviewEvaluationLLMOutput.model_validate(result)

    async def _summarize(
        self, details: list[QuestionEvaluationDTO], overall_score: int, provider: str | None
    ) -> InterviewEvaluationSummaryLLMOutput:
        try:
            prompt = await load_prompt("interview-report-summary", False)
            chain = prompt | (await self._model(provider)).with_structured_output(InterviewEvaluationSummaryLLMOutput)
            result = await chain.ainvoke({
                "overallScore": overall_score,
                "evaluationDetails": json.dumps(
                    [item.model_dump(by_alias=True) for item in details], ensure_ascii=False
                ),
            })
            return result if isinstance(result, InterviewEvaluationSummaryLLMOutput) else InterviewEvaluationSummaryLLMOutput.model_validate(result)
        except Exception as error:
            logger.warning("面试总结生成失败，使用确定性总结: %s", error)
            answered = sum(1 for item in details if item.user_answer and item.user_answer.strip())
            return InterviewEvaluationSummaryLLMOutput(
                overall_feedback=f"本次面试共评估 {len(details)} 题，完成作答 {answered} 题，综合得分 {overall_score}。",
                strengths=["已完成的回答体现了相应技术理解"] if answered else [],
                improvements=["优先补全未作答题目，并结合原理与工程案例组织回答"],
            )

    def _merge_evaluations(
        self, outputs: list[InterviewEvaluationLLMOutput], questions: list[InterviewQuestionDTO]
    ) -> tuple[list[QuestionEvaluationDTO], list[ReferenceAnswerDTO]]:
        evaluated = {item.question_index: item for output in outputs for item in output.question_evaluations}
        details: list[QuestionEvaluationDTO] = []
        refs: list[ReferenceAnswerDTO] = []
        for question in questions:
            item = evaluated.get(question.question_index)
            answered = bool(question.user_answer and question.user_answer.strip())
            score = max(0, min(100, int(item.score))) if item is not None and answered else 0
            feedback = item.feedback if item is not None and answered else ("未作答，计 0 分" if not answered else "评估失败，计 0 分")
            reference_answer = item.reference_answer if item is not None else (question.reference_answer or "暂无参考答案")
            key_points = item.key_points if item is not None else question.key_points
            details.append(QuestionEvaluationDTO(
                question_index=question.question_index, question=question.question,
                category=question.category, user_answer=question.user_answer,
                score=score, feedback=feedback,
            ))
            refs.append(ReferenceAnswerDTO(
                question_index=question.question_index, question=question.question,
                reference_answer=reference_answer, key_points=key_points,
            ))
        return details, refs

    @staticmethod
    def _category_scores(details: list[QuestionEvaluationDTO]) -> list[CategoryScoreDTO]:
        grouped: dict[str, list[int]] = {}
        for item in details:
            grouped.setdefault(item.category, []).append(item.score)
        return [CategoryScoreDTO(
            category=category,
            score=round(sum(scores) / len(scores)),
            question_count=len(scores),
        ) for category, scores in grouped.items()]

    def _fallback_report(self, session_id: str, questions: list[InterviewQuestionDTO]) -> InterviewReportDTO:
        details, refs = self._merge_evaluations([], questions)
        return InterviewReportDTO(
            session_id=session_id, total_questions=len(questions), overall_score=0,
            category_scores=self._category_scores(details),
            overall_feedback="评估服务暂不可用，请稍后重试", strengths=[],
            improvements=["请稍后重新生成报告"], question_details=details,
            reference_answers=refs,
        )

    async def _node_prepare_evaluate_context(self, state: InterviewEvaluateGraphState) -> Command:
        if not state.questions:
            return Command(update={"error_message": "empty_questions"}, goto="fallback_report")
        return Command(update={"error_message": None}, goto="evaluate_answers")

    async def _node_evaluate_answers(self, state: InterviewEvaluateGraphState, config: RunnableConfig) -> Command:
        try:
            output = await self._evaluate_batch(
                state.questions, state.resume_text, state.llm_provider, state.reference_context
            )
            details, refs = self._merge_evaluations([output], state.questions)
            report = InterviewReportDTO(
                session_id=state.session_id, total_questions=len(state.questions),
                overall_score=round(sum(item.score for item in details) / len(details)),
                category_scores=self._category_scores(details),
                overall_feedback=output.overall_feedback, strengths=output.strengths,
                improvements=output.improvements, question_details=details, reference_answers=refs,
            )
            return Command(update={"report": report, "error_message": None}, goto="__end__")
        except Exception as error:
            return Command(update={"error_message": str(error)}, goto="fallback_report")

    async def _node_fallback_report(self, state: InterviewEvaluateGraphState) -> Command:
        return Command(update={"report": self._fallback_report(state.session_id, state.questions)}, goto="__end__")

    async def _model(self, provider: str | None) -> Any:
        return self._chat_model or await self.llm_provider_resolver.resolve(provider)

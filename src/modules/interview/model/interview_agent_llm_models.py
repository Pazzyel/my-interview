from pydantic import Field

from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class InterviewQuestionLLMItem(BaseCamelSchema):
    """Structured question produced by the interviewer model."""

    question: str
    type: str
    category: str
    topic_summary: str | None = None
    follow_ups: list[str] = Field(default_factory=list)


class InterviewQuestionLLMOutput(BaseCamelSchema):
    questions: list[InterviewQuestionLLMItem]


class InterviewEvaluationLLMItem(BaseCamelSchema):
    """Structured evaluation for one interview question."""

    question_index: int
    score: int
    feedback: str
    reference_answer: str
    key_points: list[str] = Field(default_factory=list)


class InterviewEvaluationLLMOutput(BaseCamelSchema):
    overall_score: int
    overall_feedback: str
    strengths: list[str]
    improvements: list[str]
    question_evaluations: list[InterviewEvaluationLLMItem]


class InterviewEvaluationSummaryLLMOutput(BaseCamelSchema):
    overall_feedback: str
    strengths: list[str]
    improvements: list[str]

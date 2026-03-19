from pydantic import BaseModel


class InterviewQuestionLLMItem(BaseModel):
    """AI面试官生成的问题"""
    question: str
    type: str
    category: str
    follow_ups: list[str] = []


class InterviewQuestionLLMOutput(BaseModel):
    questions: list[InterviewQuestionLLMItem]


class InterviewEvaluationLLMItem(BaseModel):
    """单个问题的苹果结果"""
    question_index: int # 问题在这轮面试的id
    score: int          # 回答的评分
    feedback: str       # 对回答的评价
    reference_answer: str # 参考回答
    key_points: list[str] = [] # 关键要点


class InterviewEvaluationLLMOutput(BaseModel):
    overall_score: int
    overall_feedback: str
    strengths: list[str]
    improvements: list[str]
    question_evaluations: list[InterviewEvaluationLLMItem]

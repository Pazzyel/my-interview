import logging
from typing import Dict, List, cast

from langchain_community.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from common.ai_config import ai_config
from infrastructure.prompt.prompt_service import load_prompt
from modules.resume.model.resume_entity import ResumeAnalysisResponse
from modules.resume.model.resume_grading_dto import ResumeAnalysisStructuredResponseDTO

logger = logging.getLogger(__name__)


class ResumeGradingService:
    """简历评分服务 / Resume grading service."""

    def __init__(self) -> None:
        self._chat_model: ChatOpenAI = ChatOpenAI(
            model=ai_config.chat_model_name,
            api_key=ai_config.chat_api_key,
            base_url=ai_config.base_url,
            temperature=0,
        )
        self._prompt_node_name: str = "resume-analysis"

    async def analyze_resume(self, resume_text: str) -> ResumeAnalysisResponse:
        """
        调用 LLM 分析简历并转换为系统内的评分 DTO。

        Analyze resume content through LLM and map structured output to internal DTO.

        流程说明 / Workflow:
        1) 读取系统与用户提示词，并注入 `resumeText` 变量。
        2) 使用结构化输出约束模型返回 JSON，减少解析失败概率。
        3) 将结构化对象映射到 `ResumeAnalysisResponse`（持久化友好的平铺字段）。
        4) 若调用失败，返回兜底响应并记录日志，避免消费者中断。
        """
        # 1. 加载统一 YAML Prompt 模板并构建链路
        try:
            structured_llm = self._chat_model.with_structured_output(ResumeAnalysisStructuredResponseDTO)
            prompt_template: ChatPromptTemplate = await load_prompt(self._prompt_node_name, False)
            chain = prompt_template | structured_llm
            llm_result: ResumeAnalysisStructuredResponseDTO = cast(
                ResumeAnalysisStructuredResponseDTO,
                await chain.ainvoke({"resumeText": resume_text, "messages": []}),
            )

            # 2. 映射响应
            mapped_suggestions: List[Dict[str, str]] = [
                {
                    "category": item.category,
                    "priority": item.priority,
                    "issue": item.issue,
                    "recommendation": item.recommendation,
                }
                for item in llm_result.suggestions
            ]
            return ResumeAnalysisResponse(
                overallScore=llm_result.overallScore,
                contentScore=llm_result.scoreDetail.contentScore,
                structureScore=llm_result.scoreDetail.structureScore,
                skillMatchScore=llm_result.scoreDetail.skillMatchScore,
                expressionScore=llm_result.scoreDetail.expressionScore,
                projectScore=llm_result.scoreDetail.projectScore,
                summary=llm_result.summary,
                strengths=llm_result.strengths,
                suggestions=mapped_suggestions,
            )
        except Exception as error:
            logger.error("Resume analysis failed: %s", str(error), exc_info=True)
            return ResumeAnalysisResponse(
                overallScore=0,
                contentScore=0,
                structureScore=0,
                skillMatchScore=0,
                expressionScore=0,
                projectScore=0,
                summary=f"分析过程中出现错误: {str(error)}",
                strengths=[],
                suggestions=[
                    {
                        "category": "系统",
                        "priority": "高",
                        "issue": "AI分析服务暂时不可用",
                        "recommendation": "请稍后重试，或检查AI服务是否正常运行",
                    }
                ],
            )

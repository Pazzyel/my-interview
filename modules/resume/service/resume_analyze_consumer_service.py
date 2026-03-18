import json
import logging
from datetime import datetime
from typing import Dict, List

from common.models import AsyncTaskStatus
from infrastructure.database.connection import async_session_factory
from modules.resume.model.resume_entity import ResumeAnalysisEntity, ResumeAnalysisResponse
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_grading_service import ResumeGradingService

logger = logging.getLogger(__name__)


class ResumeAnalyzeConsumerService:
    """简历分析消费者业务服务 / Business service for resume analyze consumer."""

    def __init__(self, resume_repository: ResumeRepository, resume_grading_service: ResumeGradingService) -> None:
        self._resume_repository: ResumeRepository = resume_repository
        self._resume_grading_service: ResumeGradingService = resume_grading_service

    async def process_task(self, resume_id: int, content: str) -> None:
        """
        中文：处理单条简历分析任务，完整执行状态流转与结果落库。
        English: Process one resume analysis task with full status transition and persistence.

        执行步骤 / Execution Steps:
        1) 检查简历是否存在，不存在则直接跳过。
        2) 标记状态为 PROCESSING，清空错误信息。
        3) 调用评分服务生成结构化分析结果。
        4) 写入 resume_analyses 历史记录。
        5) 标记简历状态为 COMPLETED。

        说明 / Notes:
        - 该方法抛出的异常会由消费者层接管并决定是否重试。
        - 所有数据库写操作都通过 repository 层执行，符合分层约束。
        """
        # 1) pre-check and mark processing
        async with async_session_factory() as db:
            exists: bool = await self._resume_repository.exists_by_id(db, resume_id)
            if not exists:
                logger.warning("Resume does not exist, skip analyze task: resumeId=%s", resume_id)
                await db.commit()
                return

            await self._resume_repository.update_analyze_status(db, resume_id, AsyncTaskStatus.PROCESSING, None)
            await db.commit()

        # 2) analyze resume text
        analysis: ResumeAnalysisResponse = await self._resume_grading_service.analyze_resume(content)

        # 3) save analysis and mark completed
        strengths_json: str = json.dumps(self._safe_strengths(analysis.strengths), ensure_ascii=False)
        suggestions_json: str = json.dumps(self._safe_suggestions(analysis.suggestions), ensure_ascii=False)
        analysis_entity: ResumeAnalysisEntity = ResumeAnalysisEntity(
            resume_id=resume_id,
            overallScore=analysis.overallScore,
            contentScore=analysis.contentScore,
            structureScore=analysis.structureScore,
            skillMatchScore=analysis.skillMatchScore,
            expressionScore=analysis.expressionScore,
            projectScore=analysis.projectScore,
            summary=analysis.summary,
            strengthsJson=strengths_json,
            suggestionsJson=suggestions_json,
            analyzedAt=datetime.now(),
        )

        async with async_session_factory() as db:
            exists_after_analyze: bool = await self._resume_repository.exists_by_id(db, resume_id)
            if not exists_after_analyze:
                logger.warning("Resume deleted during analysis, skip saving: resumeId=%s", resume_id)
                await db.commit()
                return

            await self._resume_repository.save_analysis(db, analysis_entity)
            await self._resume_repository.update_analyze_status(db, resume_id, AsyncTaskStatus.COMPLETED, None)
            await db.commit()

        logger.info("Resume analysis completed: resumeId=%s, score=%s", resume_id, analysis.overallScore)

    async def mark_failed(self, resume_id: int, error_message: str) -> None:
        """Mark resume analyze status as FAILED with truncated error message."""
        truncated_error: str = error_message[:500] if len(error_message) > 500 else error_message
        async with async_session_factory() as db:
            await self._resume_repository.update_analyze_status(
                db,
                resume_id,
                AsyncTaskStatus.FAILED,
                truncated_error,
            )
            await db.commit()

    def _safe_strengths(self, strengths: List[str] | None) -> List[str]:
        """Normalize strengths into string list."""
        if strengths is None:
            return []
        return strengths

    def _safe_suggestions(self, suggestions: List[Dict[str, str]] | None) -> List[Dict[str, str]]:
        """Normalize suggestions into dict list."""
        if suggestions is None:
            return []
        return suggestions

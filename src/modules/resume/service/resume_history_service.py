import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.interview.repository.interview_repository import InterviewRepository
from modules.resume.model.resume_history_dto import ResumeAnalysisHistoryDTO, ResumeDetailDTO, ResumeListItemDTO
from modules.resume.repository.resume_repository import ResumeRepository


class ResumeHistoryService:
    """
    简历历史服务，负责列表和详情查询。
    Resume history service for listing and detail query.
    """

    def __init__(self, resume_repository: ResumeRepository, interview_repository: InterviewRepository) -> None:
        self.resume_repository = resume_repository
        self.interview_repository = interview_repository

    async def get_all_resumes(self, db: AsyncSession) -> list[ResumeListItemDTO]:
        """
        生成简历列表展示数据（含最新评分、最近分析时间与面试次数）。
        Build resume list display DTOs with latest score, last analysis time, and interview count.
        """
        resume_list = await self.resume_repository.find_all_ordered(db)

        result: list[ResumeListItemDTO] = []
        for resume in resume_list:
            if resume.id is None:
                continue

            latest_analysis = await self.resume_repository.get_latest_analysis_as_dto(db, resume.id)
            latest_score: int | None = latest_analysis.overallScore if latest_analysis else None

            analysis_entity_list = await self.resume_repository.find_analyses_by_resume_id(db, resume.id)
            last_analyzed_at = analysis_entity_list[0].analyzedAt if len(analysis_entity_list) > 0 else None
            interview_count: int = await self.interview_repository.count_by_resume_id(db, resume.id)

            result.append(
                ResumeListItemDTO(
                    id=resume.id,
                    filename=resume.originalFilename,
                    fileSize=resume.fileSize,
                    uploadedAt=resume.uploadedAt,
                    accessCount=resume.accessCount,
                    latestScore=latest_score,
                    lastAnalyzedAt=last_analyzed_at,
                    interviewCount=interview_count,
                )
            )

        return result

    async def get_resume_detail(self, db: AsyncSession, resume_id: int) -> ResumeDetailDTO:
        """
        生成单份简历详情数据（含分析历史与面试历史）。
        Build resume detail DTO including analysis history and interview history.
        """
        resume = await self.resume_repository.find_by_id(db, resume_id)
        if resume is None or resume.id is None:
            raise BusinessException(ErrorCode.RESUME_NOT_FOUND, "简历不存在")

        analysis_entities = await self.resume_repository.find_analyses_by_resume_id(db, resume_id)
        analyses: list[ResumeAnalysisHistoryDTO] = [self._to_analysis_dto(entity) for entity in analysis_entities]

        interview_history = await self.interview_repository.list_history_by_resume_id(db, resume_id)

        return ResumeDetailDTO(
            id=resume.id,
            filename=resume.originalFilename,
            fileSize=resume.fileSize,
            contentType=resume.contentType,
            storageUrl=resume.storageUrl,
            uploadedAt=resume.uploadedAt,
            accessCount=resume.accessCount,
            resumeText=resume.resumeText,
            analyzeStatus=resume.analyzeStatus,
            analyzeError=resume.analyzeError,
            analyses=analyses,
            interviews=[item.model_dump() for item in interview_history],
        )

    def _to_analysis_dto(self, entity: Any) -> ResumeAnalysisHistoryDTO:
        """
        将分析实体转换为历史 DTO，并完成 strengths/suggestions 的 JSON 反序列化。
        Convert analysis entity to history DTO and deserialize strengths/suggestions JSON fields.
        """
        strengths: list[str] = []
        suggestions: list[Any] = []

        if entity.strengthsJson:
            try:
                strengths_data: Any = json.loads(entity.strengthsJson)
                if isinstance(strengths_data, list):
                    strengths = [str(item) for item in strengths_data]
            except json.JSONDecodeError:
                strengths = []

        if entity.suggestionsJson:
            try:
                suggestions_data: Any = json.loads(entity.suggestionsJson)
                if isinstance(suggestions_data, list):
                    suggestions = suggestions_data
            except json.JSONDecodeError:
                suggestions = []

        return ResumeAnalysisHistoryDTO(
            id=entity.id,
            overallScore=entity.overallScore,
            contentScore=entity.contentScore,
            structureScore=entity.structureScore,
            skillMatchScore=entity.skillMatchScore,
            expressionScore=entity.expressionScore,
            projectScore=entity.projectScore,
            summary=entity.summary,
            analyzedAt=entity.analyzedAt,
            strengths=strengths,
            suggestions=suggestions,
        )

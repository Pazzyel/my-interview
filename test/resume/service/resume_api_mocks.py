import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from common.models import AsyncTaskStatus
from modules.resume.model.resume_entity import ResumeAnalysisEntity, ResumeAnalysisResponse, ResumeEntity
from modules.resume.model.resume_history_dto import ResumeAnalysisHistoryDTO, ResumeDetailDTO, ResumeListItemDTO


class DummyInterviewHistoryItem:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, Any]:
        return self._payload


class FakeResumeRepository:
    def __init__(self) -> None:
        self._resumes: dict[int, ResumeEntity] = {}
        self._hash_index: dict[str, int] = {}
        self._analyses: dict[int, list[ResumeAnalysisEntity]] = {}

    def add_resume(self, resume: ResumeEntity, file_hash: str | None = None) -> None:
        if resume.id is None:
            raise ValueError("resume.id cannot be None")
        self._resumes[resume.id] = resume
        self._hash_index[file_hash or resume.fileHash] = resume.id

    def add_analysis(self, resume_id: int, analysis: ResumeAnalysisEntity) -> None:
        self._analyses.setdefault(resume_id, []).insert(0, analysis)

    async def find_by_hash(self, db: Any, file_hash: str) -> ResumeEntity | None:
        resume_id = self._hash_index.get(file_hash)
        if resume_id is None:
            return None
        return self._resumes.get(resume_id)

    async def save(self, db: Any, resume: ResumeEntity) -> ResumeEntity:
        if resume.id is None:
            resume.id = max(self._resumes.keys(), default=0) + 1
        self._resumes[resume.id] = resume
        self._hash_index[resume.fileHash] = resume.id
        return resume

    async def get_latest_analysis_as_dto(self, db: Any, resume_id: int) -> ResumeAnalysisResponse | None:
        analysis_list = self._analyses.get(resume_id, [])
        if not analysis_list:
            return None

        latest = analysis_list[0]
        strengths = json.loads(latest.strengthsJson) if latest.strengthsJson else []
        suggestions = json.loads(latest.suggestionsJson) if latest.suggestionsJson else []

        return ResumeAnalysisResponse(
            overallScore=latest.overallScore,
            contentScore=latest.contentScore,
            structureScore=latest.structureScore,
            skillMatchScore=latest.skillMatchScore,
            expressionScore=latest.expressionScore,
            projectScore=latest.projectScore,
            summary=latest.summary,
            strengths=strengths,
            suggestions=suggestions,
        )

    async def find_all_ordered(self, db: Any) -> list[ResumeEntity]:
        return sorted(self._resumes.values(), key=lambda item: item.uploadedAt, reverse=True)

    async def find_analyses_by_resume_id(self, db: Any, resume_id: int) -> list[ResumeAnalysisEntity]:
        return self._analyses.get(resume_id, [])

    async def find_by_id(self, db: Any, resume_id: int) -> ResumeEntity | None:
        return self._resumes.get(resume_id)

    async def update_analyze_status(
        self,
        db: Any,
        resume_id: int,
        status: AsyncTaskStatus,
        analyze_error: str | None,
    ) -> bool:
        resume = self._resumes.get(resume_id)
        if resume is None:
            return False

        resume.analyzeStatus = status
        resume.analyzeError = analyze_error
        return True

    async def delete_by_id(self, db: Any, resume_id: int) -> None:
        resume = self._resumes.pop(resume_id, None)
        if resume is not None:
            self._hash_index.pop(resume.fileHash, None)
        self._analyses.pop(resume_id, None)


class FakeInterviewRepository:
    def __init__(self, counts: dict[int, int], history: dict[int, list[DummyInterviewHistoryItem]]) -> None:
        self._counts = counts
        self._history = history

    async def count_by_resume_id(self, db: Any, resume_id: int) -> int:
        return self._counts.get(resume_id, 0)

    async def list_history_by_resume_id(self, db: Any, resume_id: int) -> list[DummyInterviewHistoryItem]:
        return self._history.get(resume_id, [])


class FakeInterviewPersistenceService:
    def __init__(self) -> None:
        self.deleted_resume_ids: list[int] = []

    async def delete_sessions_by_resume_id(self, db: Any, resume_id: int) -> None:
        self.deleted_resume_ids.append(resume_id)


class FakeFileValidationService:
    async def validate_file(self, file: Any, max_bytes: int, field_name: str) -> int:
        return 1024

    def validate_content_type_by_list(self, content_type: str, allowed_types: list[str], message: str) -> None:
        return None


class FakeFileHashService:
    async def calculate_hash_file(self, file: Any) -> str:
        return f"hash:{file.filename}"


class FakeParseService:
    def detect_content_type(self, file: Any) -> str:
        return "application/pdf"

    async def parse_resume(self, file: Any) -> str:
        return f"parsed text for {file.filename}"


class FakeFileStorageService:
    def __init__(self) -> None:
        self.deleted_keys: list[str] = []

    async def upload_resume(self, file: Any) -> str:
        return f"resume/{file.filename}"

    async def get_file_url(self, file_key: str) -> str:
        return f"https://mock-storage.local/{file_key}"

    async def delete_file(self, key: str) -> None:
        self.deleted_keys.append(key)


class FakeAnalyzeMessageProducer:
    def __init__(self) -> None:
        self.sent_tasks: list[tuple[int, str]] = []

    def send_analyze_task(self, resume_id: int, content: str) -> None:
        self.sent_tasks.append((resume_id, content))


class MockResumeUploadService:
    def __init__(
        self,
        parse_service: FakeParseService,
        storage_service: FakeFileStorageService,
        file_validation_service: FakeFileValidationService,
        file_hash_service: FakeFileHashService,
        analyze_stream_producer: FakeAnalyzeMessageProducer,
        resume_repository: FakeResumeRepository,
    ) -> None:
        self.parse_service = parse_service
        self.storage_service = storage_service
        self.file_validation_service = file_validation_service
        self.file_hash_service = file_hash_service
        self.analyze_stream_producer = analyze_stream_producer
        self.resume_repository = resume_repository

    async def upload_and_analyze(self, db: Any, file: Any) -> dict[str, Any]:
        await self.file_validation_service.validate_file(file, 10 * 1024 * 1024, "Resume")
        content_type = self.parse_service.detect_content_type(file)
        self.file_validation_service.validate_content_type_by_list(content_type, ["application/pdf"], "")

        file_hash = await self.file_hash_service.calculate_hash_file(file)
        existing_resume = await self.resume_repository.find_by_hash(db, file_hash)

        if existing_resume is not None:
            analysis = await self.resume_repository.get_latest_analysis_as_dto(db, existing_resume.id or 0)
            if analysis:
                return {
                    "analysis": analysis.model_dump(),
                    "storage": {
                        "fileKey": existing_resume.storageKey or "",
                        "fileUrl": existing_resume.storageUrl or "",
                        "resumeId": existing_resume.id,
                    },
                    "duplicate": True,
                }

            return {
                "resume": {
                    "id": existing_resume.id,
                    "filename": existing_resume.originalFilename,
                    "analyzeStatus": existing_resume.analyzeStatus.value,
                },
                "storage": {
                    "fileKey": existing_resume.storageKey or "",
                    "fileUrl": existing_resume.storageUrl or "",
                    "resumeId": existing_resume.id,
                },
                "duplicate": True,
            }

        resume_text = await self.parse_service.parse_resume(file)
        file_key = await self.storage_service.upload_resume(file)
        file_url = await self.storage_service.get_file_url(file_key)
        new_resume = ResumeEntity(
            fileHash=file_hash,
            originalFilename=file.filename,
            fileSize=1024,
            contentType=content_type,
            storageKey=file_key,
            storageUrl=file_url,
            resumeText=resume_text,
            analyzeStatus=AsyncTaskStatus.PENDING,
        )
        saved_resume = await self.resume_repository.save(db, new_resume)
        self.analyze_stream_producer.send_analyze_task(saved_resume.id or 0, resume_text)

        return {
            "resume": {
                "id": saved_resume.id,
                "filename": saved_resume.originalFilename,
                "analyzeStatus": saved_resume.analyzeStatus.value,
            },
            "storage": {
                "fileKey": file_key,
                "fileUrl": file_url,
                "resumeId": saved_resume.id,
            },
            "duplicate": False,
        }

    async def reanalyze(self, db: Any, resume_id: int) -> None:
        resume = await self.resume_repository.find_by_id(db, resume_id)
        if resume is None:
            raise ValueError("resume not found")
        await self.resume_repository.update_analyze_status(db, resume_id, AsyncTaskStatus.PENDING, None)
        self.analyze_stream_producer.send_analyze_task(resume_id, resume.resumeText or "")


class MockResumeHistoryService:
    def __init__(self, resume_repository: FakeResumeRepository, interview_repository: FakeInterviewRepository) -> None:
        self.resume_repository = resume_repository
        self.interview_repository = interview_repository

    async def get_all_resumes(self, db: Any) -> list[ResumeListItemDTO]:
        resumes = await self.resume_repository.find_all_ordered(db)
        result: list[ResumeListItemDTO] = []
        for resume in resumes:
            if resume.id is None:
                continue
            latest_analysis = await self.resume_repository.get_latest_analysis_as_dto(db, resume.id)
            analysis_entities = await self.resume_repository.find_analyses_by_resume_id(db, resume.id)
            interview_count = await self.interview_repository.count_by_resume_id(db, resume.id)
            result.append(
                ResumeListItemDTO(
                    id=resume.id,
                    filename=resume.originalFilename,
                    fileSize=resume.fileSize,
                    uploadedAt=resume.uploadedAt,
                    accessCount=resume.accessCount,
                    latestScore=latest_analysis.overallScore if latest_analysis else None,
                    lastAnalyzedAt=analysis_entities[0].analyzedAt if analysis_entities else None,
                    interviewCount=interview_count,
                )
            )
        return result

    async def get_resume_detail(self, db: Any, resume_id: int) -> ResumeDetailDTO:
        resume = await self.resume_repository.find_by_id(db, resume_id)
        if resume is None or resume.id is None:
            raise ValueError("resume not found")

        analysis_entities = await self.resume_repository.find_analyses_by_resume_id(db, resume_id)
        analyses = [
            ResumeAnalysisHistoryDTO(
                id=item.id or 0,
                overallScore=item.overallScore,
                contentScore=item.contentScore,
                structureScore=item.structureScore,
                skillMatchScore=item.skillMatchScore,
                expressionScore=item.expressionScore,
                projectScore=item.projectScore,
                summary=item.summary,
                analyzedAt=item.analyzedAt,
                strengths=json.loads(item.strengthsJson or "[]"),
                suggestions=json.loads(item.suggestionsJson or "[]"),
            )
            for item in analysis_entities
        ]
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


class MockResumeDeleteService:
    def __init__(
        self,
        resume_repository: FakeResumeRepository,
        interview_persistence_service: FakeInterviewPersistenceService,
        file_storage_service: FakeFileStorageService,
    ) -> None:
        self.resume_repository = resume_repository
        self.interview_persistence_service = interview_persistence_service
        self.file_storage_service = file_storage_service

    async def delete_resume(self, db: Any, resume_id: int) -> None:
        resume = await self.resume_repository.find_by_id(db, resume_id)
        if resume is None:
            raise ValueError("resume not found")
        if resume.storageKey:
            await self.file_storage_service.delete_file(resume.storageKey)
        await self.interview_persistence_service.delete_sessions_by_resume_id(db, resume_id)
        await self.resume_repository.delete_by_id(db, resume_id)


@dataclass
class ResumeApiTestContext:
    resume_repository: FakeResumeRepository
    interview_repository: FakeInterviewRepository
    interview_persistence_service: FakeInterviewPersistenceService
    storage_service: FakeFileStorageService
    analyze_producer: FakeAnalyzeMessageProducer
    upload_service: MockResumeUploadService
    history_service: MockResumeHistoryService
    delete_service: MockResumeDeleteService


def create_resume_api_test_context() -> ResumeApiTestContext:
    now = datetime.now()

    resume_repository = FakeResumeRepository()
    existing_resume = ResumeEntity(
        id=1,
        fileHash="hash:existing.pdf",
        originalFilename="existing.pdf",
        fileSize=2048,
        contentType="application/pdf",
        storageKey="resume/existing.pdf",
        storageUrl="https://mock-storage.local/resume/existing.pdf",
        resumeText="existing resume text",
        uploadedAt=now - timedelta(days=1),
        accessCount=3,
        analyzeStatus=AsyncTaskStatus.COMPLETED,
    )
    resume_repository.add_resume(existing_resume)

    existing_analysis = ResumeAnalysisEntity(
        id=10,
        resume_id=1,
        overallScore=88,
        contentScore=86,
        structureScore=90,
        skillMatchScore=87,
        expressionScore=89,
        projectScore=88,
        summary="整体表现良好",
        strengthsJson='["结构清晰", "项目描述具体"]',
        suggestionsJson='[{"category": "表达", "priority": "中", "issue": "措辞可更精炼", "recommendation": "减少冗余句"}]',
        analyzedAt=now - timedelta(hours=2),
    )
    resume_repository.add_analysis(1, existing_analysis)

    interview_repository = FakeInterviewRepository(
        counts={1: 2},
        history={
            1: [
                DummyInterviewHistoryItem(
                    {
                        "sessionId": "session-1",
                        "score": 90,
                        "createdAt": (now - timedelta(hours=1)).isoformat(),
                    }
                )
            ]
        },
    )

    interview_persistence_service = FakeInterviewPersistenceService()
    storage_service = FakeFileStorageService()
    analyze_producer = FakeAnalyzeMessageProducer()

    upload_service = MockResumeUploadService(
        parse_service=FakeParseService(),
        storage_service=storage_service,
        file_validation_service=FakeFileValidationService(),
        file_hash_service=FakeFileHashService(),
        analyze_stream_producer=analyze_producer,
        resume_repository=resume_repository,
    )
    history_service = MockResumeHistoryService(resume_repository, interview_repository)
    delete_service = MockResumeDeleteService(
        resume_repository=resume_repository,
        interview_persistence_service=interview_persistence_service,
        file_storage_service=storage_service,
    )

    return ResumeApiTestContext(
        resume_repository=resume_repository,
        interview_repository=interview_repository,
        interview_persistence_service=interview_persistence_service,
        storage_service=storage_service,
        analyze_producer=analyze_producer,
        upload_service=upload_service,
        history_service=history_service,
        delete_service=delete_service,
    )

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeSessionContext:
    def __init__(self, session: _FakeAsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeAsyncSession:
        return self._session

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.sessions: list[_FakeAsyncSession] = []

    def __call__(self) -> _FakeSessionContext:
        session = _FakeAsyncSession()
        self.sessions.append(session)
        return _FakeSessionContext(session)
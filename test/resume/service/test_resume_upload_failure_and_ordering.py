import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import UploadFile

from common.exceptions import BusinessException, ErrorCode
from infrastructure.file.document_parse_service import DocumentParseError
from modules.resume.model.resume_entity import ResumeEntity
from modules.resume.service.resume_parse_service import ResumeParseService
from modules.resume.service.resume_upload_service import ResumeUploadService


def _upload_file() -> UploadFile:
    return UploadFile(
        filename="resume.pdf",
        file=BytesIO(b"pdf-content"),
        headers={"content-type": "application/pdf"},
    )


def test_resume_parse_error_is_reported_as_business_error() -> None:
    document_parser = SimpleNamespace(
        parse_content=AsyncMock(side_effect=DocumentParseError("missing PDF dependency"))
    )
    service = ResumeParseService(document_parser, Mock())

    with pytest.raises(BusinessException) as raised:
        asyncio.run(service.parse_resume(_upload_file()))

    assert raised.value.code == ErrorCode.RESUME_PARSE_FAILED


def test_parse_failure_does_not_store_persist_or_publish() -> None:
    parse_service = SimpleNamespace(
        detect_content_type=Mock(return_value="application/pdf"),
        parse_resume=AsyncMock(
            side_effect=BusinessException(ErrorCode.RESUME_PARSE_FAILED, "parse failed")
        ),
    )
    storage_service = SimpleNamespace(
        upload_resume=AsyncMock(),
        get_file_url=AsyncMock(),
    )
    repository = SimpleNamespace(
        find_by_hash=AsyncMock(return_value=None),
        save=AsyncMock(),
    )
    producer = SimpleNamespace(send_analyze_task=Mock())
    service = ResumeUploadService(
        parse_service=parse_service,
        storage_service=storage_service,
        file_validation_service=SimpleNamespace(
            validate_file=AsyncMock(return_value=11),
            validate_content_type_by_list=Mock(),
        ),
        file_hash_service=SimpleNamespace(calculate_hash_file=AsyncMock(return_value="hash")),
        analyze_stream_producer=producer,
        resume_repository=repository,
    )

    with pytest.raises(BusinessException):
        asyncio.run(service.upload_and_analyze(AsyncMock(), _upload_file()))

    storage_service.upload_resume.assert_not_awaited()
    repository.save.assert_not_awaited()
    producer.send_analyze_task.assert_not_called()


def test_resume_is_committed_before_analysis_message_is_published() -> None:
    events: list[str] = []
    db = AsyncMock()

    async def commit() -> None:
        events.append("commit")

    db.commit.side_effect = commit

    async def save(_db, resume: ResumeEntity) -> ResumeEntity:
        resume.id = 42
        events.append("save")
        return resume

    def publish(resume_id: int, content: str) -> None:
        assert resume_id == 42
        assert content == "parsed resume"
        events.append("publish")

    service = ResumeUploadService(
        parse_service=SimpleNamespace(
            detect_content_type=Mock(return_value="application/pdf"),
            parse_resume=AsyncMock(return_value="parsed resume"),
        ),
        storage_service=SimpleNamespace(
            upload_resume=AsyncMock(return_value="resumes/resume.pdf"),
            get_file_url=AsyncMock(return_value="https://storage/resume.pdf"),
        ),
        file_validation_service=SimpleNamespace(
            validate_file=AsyncMock(return_value=11),
            validate_content_type_by_list=Mock(),
        ),
        file_hash_service=SimpleNamespace(calculate_hash_file=AsyncMock(return_value="hash")),
        analyze_stream_producer=SimpleNamespace(send_analyze_task=Mock(side_effect=publish)),
        resume_repository=SimpleNamespace(
            find_by_hash=AsyncMock(return_value=None),
            save=AsyncMock(side_effect=save),
        ),
    )

    asyncio.run(service.upload_and_analyze(db, _upload_file()))

    assert events == ["save", "commit", "publish"]

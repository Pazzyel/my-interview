import logging

from fastapi import UploadFile

from common.exceptions import BusinessException, ErrorCode
from infrastructure.file.document_parse_service import DocumentParseError, DocumentParseService
from infrastructure.file.file_storage_service import FileStorageService

logger = logging.getLogger(__name__)

class ResumeParseService:
    def __init__(self, document_parse_service: DocumentParseService, storage_service: FileStorageService):
        self.document_parse_service = document_parse_service
        self.storage_service = storage_service

    async def parse_resume(self, file: UploadFile) -> str:
        """
        解析简历文本内容

        Parse uploaded resume file and extract text.
        """
        logger.info(f"Start parsing resume file: {file.filename}")
        try:
            return await self.document_parse_service.parse_content(file)
        except DocumentParseError as error:
            raise BusinessException(
                ErrorCode.RESUME_PARSE_FAILED,
                "无法解析简历文件，请确认文件内容和格式正确",
                details=str(error),
            ) from error

    def detect_content_type(self, file: UploadFile) -> str:
        """
        解析文件类型（MIME）

        Detect MIME type of file.
        """
        return self.document_parse_service.detect_content_type(file)

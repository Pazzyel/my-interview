import logging

from fastapi import UploadFile

from infrastructure.file.document_parse_service import DocumentParseService
from infrastructure.file.file_storage_service import FileStorageService

logger = logging.getLogger(__name__)


class KnowledgeBaseParseService:
    """
    知识库解析服务

    Thin wrapper delegating to DocumentParseService and FileStorageService.
    """
    def __init__(
        self,
        document_parse_service: DocumentParseService,
        storage_service: FileStorageService,
    ):
        self.document_parse_service: DocumentParseService = document_parse_service
        self.storage_service: FileStorageService = storage_service

    async def parse_content(self, file: UploadFile) -> str:
        """
        解析上传的知识库文件，提取文本内容。

        Parse uploaded knowledge base file and extract text content.
        Supports PDF, DOCX, DOC, TXT, MD etc.
        """
        logger.info("开始解析知识库文件: %s", file.filename)
        return await self.document_parse_service.parse_content(file)


    async def parse_content_from_bytes(self, content: bytes, file_name: str) -> str:
        """
        解析上传的知识库文件字节数组，提取文本内容。

        Parse uploaded knowledge base file and extract text content.
        Supports PDF, DOCX, DOC, TXT, MD etc.
        """
        logger.info("开始解析知识库文件: %s", file_name)
        return await self.document_parse_service.parse_content_from_bytes(content, file_name)

    def detect_content_type(self, file: UploadFile) -> str:
        """检测文件的MIME类型"""
        return self.document_parse_service.detect_content_type(file)

import logging
from typing import Dict, Any

from fastapi import UploadFile

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode
from infrastructure.file.file_hash_service import FileHashService
from infrastructure.file.file_storage_service import FileStorageService
from infrastructure.file.file_validation_service import FileValidationService
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.model.resume_entity import ResumeEntity
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_parse_service import ResumeParseService

logger = logging.getLogger(__name__)

class ResumeUploadService:
    def __init__(
        self,
        parse_service: ResumeParseService,
        storage_service: FileStorageService,
        file_validation_service: FileValidationService,
        file_hash_service: FileHashService,
        analyze_stream_producer: AnalyzeMessageProducer,
        resume_repository: ResumeRepository
    ):
        self.parse_service = parse_service
        self.storage_service = storage_service
        self.file_validation_service = file_validation_service
        self.file_hash_service = file_hash_service
        self.analyze_stream_producer = analyze_stream_producer
        self.resume_repository = resume_repository

    async def upload_and_analyze(self, file: UploadFile) -> Dict[str, Any]:
        """
        上传分析文件逻辑
        Main logic for uploading and analyzing logic (async part streamed to workers)
        """
        # 保证文件大小符合要求
        # Validate file size conceptually (reading bytes)
        # content = await file.read()

        file_size: int = await self.file_validation_service.validate_file(file, app_config.max_file_size_bytes, "Resume")
        
        # 保证文件类型符合要求
        content_type = self.parse_service.detect_content_type(file)
        self.file_validation_service.validate_content_type_by_list(
            content_type, 
            app_config.allowed_types, 
            f"Unsupported file type: {content_type}"
        )

        logger.info(f"Received resume upload request: {file.filename}")

        # 根据文件内容计算哈希值
        # Hash for deduplication
        file_hash = await self.file_hash_service.calculate_hash_file(file)
        # 如果有重复文件，不用保存，增加一次计数
        existing_resume = await self.resume_repository.find_by_hash(file_hash)
        if existing_resume:
            return await self.handle_duplicate_resume(existing_resume)

        # unstructured解析文件的文本内容
        # Parse Text
        resume_text = await self.parse_service.parse_resume(file)
        if not resume_text or not resume_text.strip():
            raise BusinessException(ErrorCode.RESUME_PARSE_FAILED, "Could not extract text from file")
        
        # 保存到RustFS
        # Storage
        file_key = await self.storage_service.upload_resume(file)
        file_url = self.storage_service.get_file_url(file_key)
        
        logger.info(f"Resume stored to RustFS: {file_key}")

        # 构建简历对象，保存到数据库
        # Persistence
        new_resume = ResumeEntity(
            fileHash=file_hash,
            originalFilename=file.filename or "unknown",
            fileSize=file_size,
            contentType=content_type,
            storageKey=file_key,
            storageUrl=file_url,
            resumeText=resume_text
        )
        
        saved_resume = await self.resume_repository.save(new_resume)

        # 发送文本AI分析异步任务到MQ
        # Publish Task
        if not saved_resume.id:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "查找出的简历文件没有id") 
        self.analyze_stream_producer.send_analyze_task(saved_resume.id, resume_text)

        logger.info(f"Resume upload completed, analysis task queued for resumeId={saved_resume.id}")

        return {
            "resume": {
                "id": saved_resume.id,
                "filename": saved_resume.originalFilename,
                "analyzeStatus": saved_resume.analyzeStatus.value
            },
            "storage": {
                "fileKey": file_key,
                "fileUrl": file_url,
                "resumeId": saved_resume.id
            },
            "duplicate": False
        }

    async def handle_duplicate_resume(self, resume: ResumeEntity) -> Dict[str, Any]:
        logger.info(f"Duplicate resume detected, returning history analysis result: resumeId={resume.id}")
        
        if not resume.id:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "查找出的简历文件没有id") 
        analysis = await self.resume_repository.get_latest_analysis_as_dto(resume.id)
        
        # 有分析就返回分析的字典
        if analysis:
            return {
                "analysis": analysis.model_dump(),
                "storage": {
                    "fileKey": resume.storageKey or "",
                    "fileUrl": resume.storageUrl or "",
                    "resumeId": resume.id
                },
                "duplicate": True
            }
        
        # 没有分析就返回简历和存储的内容
        return {
            "resume": {
                "id": resume.id,
                "filename": resume.originalFilename,
                "analyzeStatus": resume.analyzeStatus.value
            },
            "storage": {
                "fileKey": resume.storageKey or "",
                "fileUrl": resume.storageUrl or "",
                "resumeId": resume.id
            },
            "duplicate": True
        }
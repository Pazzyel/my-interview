from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_async_session
from infrastructure.file.document_parse_service import DocumentParseService
from infrastructure.file.file_hash_service import FileHashService
from infrastructure.file.file_storage_service import FileStorageService
from infrastructure.file.file_validation_service import FileValidationService
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_parse_service import ResumeParseService
from modules.resume.service.resume_upload_service import ResumeUploadService

def get_resume_repository(db: AsyncSession = Depends(get_async_session)):
    return ResumeRepository(db=db)

def get_file_storage_service():
    return FileStorageService()

def get_file_hash_service():
    return FileHashService()

def get_document_parse_service():
    return DocumentParseService()

def get_file_validation_service():
    return FileValidationService()

def get_analyze_message_producer(
    resume_repository: ResumeRepository = Depends(get_resume_repository),
):
    return AnalyzeMessageProducer(resume_repository)

def get_resume_parse_service(
    document_parse_service: DocumentParseService = Depends(get_document_parse_service),
    storage_service: FileStorageService = Depends(get_file_storage_service)
):
    return ResumeParseService(document_parse_service, storage_service)

def get_resume_upload_service(
    parse_service: ResumeParseService = Depends(get_resume_parse_service),
    storage_service: FileStorageService = Depends(get_file_storage_service),
    file_validation_service: FileValidationService = Depends(get_file_validation_service),
    file_hash_service: FileHashService = Depends(get_file_hash_service),
    analyze_stream_producer: AnalyzeMessageProducer = Depends(get_analyze_message_producer),
    resume_repository: ResumeRepository = Depends(get_resume_repository)
):
    return ResumeUploadService(
        parse_service, 
        storage_service, 
        file_validation_service,
        file_hash_service,
        analyze_stream_producer, 
        resume_repository
    )

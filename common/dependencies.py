from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_async_session
from infrastructure.file.document_parse_service import DocumentParseService
from infrastructure.file.file_hash_service import FileHashService
from infrastructure.file.file_storage_service import FileStorageService
from infrastructure.file.file_validation_service import FileValidationService
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_parse_service import ResumeParseService
from modules.resume.service.resume_upload_service import ResumeUploadService

# ────── Knowledge Base imports ──────
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.service.knowledgebase_parse_service import KnowledgeBaseParseService
from modules.knowledgebase.service.knowledgebase_persistence_service import KnowledgeBasePersistenceService
from modules.knowledgebase.service.knowledgebase_upload_service import KnowledgeBaseUploadService
from modules.knowledgebase.listener.vectorize_message_producer import VectorizeMessageProducer

# ==================== Shared Infrastructure ====================

def get_file_storage_service():
    return FileStorageService()

def get_file_hash_service():
    return FileHashService()

def get_document_parse_service():
    return DocumentParseService()

def get_file_validation_service():
    return FileValidationService()

# ==================== Resume Module ====================

def get_resume_repository(db: AsyncSession = Depends(get_async_session)):
    return ResumeRepository(db=db)

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

# ==================== Knowledge Base Module ====================

def get_knowledgebase_repository(db: AsyncSession = Depends(get_async_session)):
    return KnowledgeBaseRepository(db=db)

def get_knowledgebase_parse_service(
    document_parse_service: DocumentParseService = Depends(get_document_parse_service),
    storage_service: FileStorageService = Depends(get_file_storage_service),
):
    return KnowledgeBaseParseService(document_parse_service, storage_service)

def get_knowledgebase_persistence_service(
    knowledgebase_repository: KnowledgeBaseRepository = Depends(get_knowledgebase_repository),
):
    return KnowledgeBasePersistenceService(knowledgebase_repository)

def get_vectorize_message_producer(
    knowledgebase_repository: KnowledgeBaseRepository = Depends(get_knowledgebase_repository),
):
    return VectorizeMessageProducer(knowledgebase_repository)

def get_knowledgebase_upload_service(
    parse_service: KnowledgeBaseParseService = Depends(get_knowledgebase_parse_service),
    persistence_service: KnowledgeBasePersistenceService = Depends(get_knowledgebase_persistence_service),
    storage_service: FileStorageService = Depends(get_file_storage_service),
    knowledgebase_repository: KnowledgeBaseRepository = Depends(get_knowledgebase_repository),
    file_validation_service: FileValidationService = Depends(get_file_validation_service),
    file_hash_service: FileHashService = Depends(get_file_hash_service),
    vectorize_stream_producer: VectorizeMessageProducer = Depends(get_vectorize_message_producer),
):
    return KnowledgeBaseUploadService(
        parse_service,
        persistence_service,
        storage_service,
        knowledgebase_repository,
        file_validation_service,
        file_hash_service,
        vectorize_stream_producer,
    )

def get_knowledgebase_vector_service():
    return KnowledgeBaseVectorService()


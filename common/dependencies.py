from infrastructure.file.document_parse_service import DocumentParseService
from infrastructure.file.file_hash_service import FileHashService
from infrastructure.file.file_storage_service import FileStorageService
from infrastructure.file.file_validation_service import FileValidationService
from modules.knowledgebase.listener.vectorize_message_producer import VectorizeMessageProducer
# ────── Knowledge Base imports ──────
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.repository.rag_chat_repository import RagChatRepository
from modules.knowledgebase.service.knowledgebase_count_service import KnowledgeBaseCountService
from modules.knowledgebase.service.knowledgebase_delete_service import KnowledgeBaseDeleteService
from modules.knowledgebase.service.knowledgebase_list_service import KnowledgeBaseListService
from modules.knowledgebase.service.knowledgebase_parse_service import KnowledgeBaseParseService
from modules.knowledgebase.service.knowledgebase_persistence_service import KnowledgeBasePersistenceService
from modules.knowledgebase.service.knowledgebase_upload_service import KnowledgeBaseUploadService
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_parse_service import ResumeParseService
from modules.resume.service.resume_upload_service import ResumeUploadService

# ==================== Shared Infrastructure ====================

file_storage_service = FileStorageService()
file_hash_service = FileHashService()
document_parse_service = DocumentParseService()
file_validation_service = FileValidationService()

# ==================== Resume Module ====================

resume_repository = ResumeRepository()
analyze_message_producer = AnalyzeMessageProducer(resume_repository)
resume_parse_service = ResumeParseService(document_parse_service, file_storage_service)

resume_upload_service = ResumeUploadService(
    resume_parse_service, 
    file_storage_service, 
    file_validation_service,
    file_hash_service,
    analyze_message_producer, 
    resume_repository
)

# ==================== Knowledge Base Module ====================

knowledgebase_repository = KnowledgeBaseRepository()
rag_chat_repository = RagChatRepository()
knowledgebase_vector_service = KnowledgeBaseVectorService()

knowledgebase_parse_service = KnowledgeBaseParseService(document_parse_service, file_storage_service)
knowledgebase_persistence_service = KnowledgeBasePersistenceService(knowledgebase_repository)
vectorize_message_producer = VectorizeMessageProducer(knowledgebase_repository)

knowledgebase_upload_service = KnowledgeBaseUploadService(
    knowledgebase_parse_service,
    knowledgebase_persistence_service,
    file_storage_service,
    knowledgebase_repository,
    file_validation_service,
    file_hash_service,
    vectorize_message_producer,
)

knowledgebase_list_service = KnowledgeBaseListService(
    knowledgebase_repository, rag_chat_repository, file_storage_service
)
knowledgebase_count_service = KnowledgeBaseCountService(knowledgebase_repository)
knowledgebase_delete_service = KnowledgeBaseDeleteService(
    knowledgebase_repository, rag_chat_repository, knowledgebase_vector_service, file_storage_service
)

from infrastructure.file.document_parse_service import DocumentParseService
from infrastructure.file.file_hash_service import FileHashService
from infrastructure.file.file_storage_service import FileStorageService
from infrastructure.file.file_validation_service import FileValidationService
from modules.interview.listener.evaluate_message_consumer import EvaluateMessageConsumer
from modules.interview.listener.evaluate_message_producer import EvaluateMessageProducer
from modules.interview.repository.interview_repository import InterviewRepository
from modules.interview.service.interview_agent_service import InterviewAgentService
from modules.interview.service.interview_evaluate_consumer_service import InterviewEvaluateConsumerService
from modules.interview.service.interview_history_service import InterviewHistoryService
from modules.interview.service.interview_persistence_service import InterviewPersistenceService
from modules.knowledgebase.listener.vectorize_message_consumer import VectorizeMessageConsumer
from modules.knowledgebase.listener.vectorize_message_producer import VectorizeMessageProducer
# ────── Knowledge Base imports ──────
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.repository.rag_chat_repository import RagChatRepository
from modules.knowledgebase.repository.rag_chat_session_repository import RagChatSessionRepository
from modules.knowledgebase.service.knowledgebase_count_service import KnowledgeBaseCountService
from modules.knowledgebase.service.knowledgebase_delete_service import KnowledgeBaseDeleteService
from modules.knowledgebase.service.knowledgebase_list_service import KnowledgeBaseListService
from modules.knowledgebase.service.knowledgebase_parse_service import KnowledgeBaseParseService
from modules.knowledgebase.service.knowledgebase_persistence_service import KnowledgeBasePersistenceService
from modules.knowledgebase.service.knowledgebase_query_service import KnowledgeBaseQueryService
from modules.knowledgebase.service.knowledgebase_upload_service import KnowledgeBaseUploadService
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService
from modules.knowledgebase.service.knowledgebase_vectorize_consumer_service import \
    KnowledgeBaseVectorizeConsumerService
from modules.knowledgebase.service.rag_chat_session_service import RagChatSessionService
from modules.resume.listener.analyze_message_consumer import AnalyzeMessageConsumer
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_analyze_consumer_service import ResumeAnalyzeConsumerService
from modules.resume.service.resume_delete_service import ResumeDeleteService
from modules.resume.service.resume_grading_service import ResumeGradingService
from modules.resume.service.resume_history_service import ResumeHistoryService
from modules.resume.service.resume_parse_service import ResumeParseService
from modules.resume.service.resume_upload_service import ResumeUploadService

# ==================== Shared Infrastructure ====================

file_storage_service = FileStorageService()
file_hash_service = FileHashService()
document_parse_service = DocumentParseService()
file_validation_service = FileValidationService()

# ==================== Resume Module ====================

resume_repository = ResumeRepository()
interview_repository = InterviewRepository()
interview_persistence_service = InterviewPersistenceService(interview_repository)
interview_history_service = InterviewHistoryService(interview_repository)
evaluate_message_producer = EvaluateMessageProducer(interview_repository)
interview_agent_service = InterviewAgentService(interview_repository, evaluate_message_producer)
interview_evaluate_consumer_service = InterviewEvaluateConsumerService(interview_agent_service, interview_repository)
evaluate_message_consumer = EvaluateMessageConsumer(interview_evaluate_consumer_service, evaluate_message_producer)

analyze_message_producer = AnalyzeMessageProducer(resume_repository)
resume_grading_service = ResumeGradingService()
resume_analyze_consumer_service = ResumeAnalyzeConsumerService(resume_repository, resume_grading_service)
analyze_message_consumer = AnalyzeMessageConsumer(resume_analyze_consumer_service, analyze_message_producer)
resume_parse_service = ResumeParseService(document_parse_service, file_storage_service)

resume_upload_service = ResumeUploadService(
    resume_parse_service, 
    file_storage_service, 
    file_validation_service,
    file_hash_service,
    analyze_message_producer, 
    resume_repository
)
resume_history_service = ResumeHistoryService(resume_repository, interview_repository)
resume_delete_service = ResumeDeleteService(
    resume_repository,
    interview_persistence_service,
    file_storage_service,
)

# ==================== Knowledge Base Module ====================

knowledgebase_repository = KnowledgeBaseRepository()
rag_chat_repository = RagChatRepository()
rag_chat_session_repository = RagChatSessionRepository()
knowledgebase_vector_service = KnowledgeBaseVectorService()

knowledgebase_parse_service = KnowledgeBaseParseService(document_parse_service, file_storage_service)
knowledgebase_persistence_service = KnowledgeBasePersistenceService(knowledgebase_repository)
vectorize_message_producer = VectorizeMessageProducer(knowledgebase_repository)
knowledgebase_vectorize_consumer_service = KnowledgeBaseVectorizeConsumerService(
    knowledgebase_repository,
    knowledgebase_vector_service,
)
vectorize_message_consumer = VectorizeMessageConsumer(
    knowledgebase_vectorize_consumer_service,
    vectorize_message_producer,
)

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
knowledgebase_query_service = KnowledgeBaseQueryService(knowledgebase_list_service, knowledgebase_vector_service, knowledgebase_count_service)
rag_chat_session_service = RagChatSessionService(rag_chat_session_repository, knowledgebase_query_service)

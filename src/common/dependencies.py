from infrastructure.file.document_parse_service import DocumentParseService
from common.config import app_config
from infrastructure.file.file_hash_service import FileHashService
from infrastructure.file.file_storage_service import FileStorageService
from infrastructure.file.file_validation_service import FileValidationService
from infrastructure.vector.milvus_vector_service import MilvusVectorService
from modules.interview.listener.evaluate_message_consumer import EvaluateMessageConsumer
from modules.interview.listener.evaluate_message_producer import EvaluateMessageProducer
from modules.interview.repository.interview_repository import InterviewRepository
from modules.interview.service.interview_agent_service import InterviewAgentService
from modules.interview.service.interview_evaluate_consumer_service import InterviewEvaluateConsumerService
from modules.interview.service.interview_history_service import InterviewHistoryService
from modules.interview.service.interview_persistence_service import InterviewPersistenceService
from modules.interview.service.interview_skill_service import InterviewSkillService
from modules.interview.service.interview_creation_coordinator import InterviewCreationCoordinator
from modules.llmprovider.repository.llm_provider_repository import (
    LlmProviderRepository,
    VoiceProviderConfigRepository,
)
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService
from modules.llmprovider.service.llm_provider_registry import LlmProviderRegistry
from modules.llmprovider.service.llm_provider_service import LlmProviderService
from modules.llmprovider.service.voice_provider_config_service import VoiceProviderConfigService
from modules.interviewschedule.repository.interview_schedule_repository import InterviewScheduleRepository
from modules.interviewschedule.service.interview_parse_service import InterviewParseService
from modules.interviewschedule.service.interview_schedule_service import InterviewScheduleService
from modules.interviewschedule.service.schedule_status_updater import ScheduleStatusUpdater
from modules.knowledgebase.listener.vectorize_message_consumer import VectorizeMessageConsumer
from modules.knowledgebase.listener.vectorize_message_producer import VectorizeMessageProducer
from modules.knowledgebase.listener.question_generation_message_consumer import QuestionGenerationMessageConsumer
from modules.knowledgebase.listener.question_generation_message_producer import QuestionGenerationMessageProducer
# ────── Knowledge Base imports ──────
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.repository.knowledgebase_question_repository import KnowledgeBaseQuestionRepository
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
from modules.knowledgebase.service.knowledgebase_interview_service import KnowledgeBaseInterviewService
from modules.knowledgebase.service.knowledgebase_question_generation_service import KnowledgeBaseQuestionGenerationService
from modules.knowledgebase.service.knowledgebase_question_service import KnowledgeBaseQuestionService
from modules.knowledgebase.service.question_generation_recovery_service import QuestionGenerationRecoveryService
from modules.knowledgebase.service.question_generation_state_service import QuestionGenerationStateService
from modules.resume.listener.analyze_message_consumer import AnalyzeMessageConsumer
from modules.resume.listener.analyze_message_producer import AnalyzeMessageProducer
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_analyze_consumer_service import ResumeAnalyzeConsumerService
from modules.resume.service.resume_delete_service import ResumeDeleteService
from modules.resume.service.resume_grading_service import ResumeGradingService
from modules.resume.service.resume_history_service import ResumeHistoryService
from modules.resume.service.resume_parse_service import ResumeParseService
from modules.resume.service.resume_upload_service import ResumeUploadService
from infrastructure.database.connection import async_session_factory
from modules.voiceinterview.listener.evaluate_message_consumer import VoiceEvaluateMessageConsumer
from modules.voiceinterview.listener.evaluate_message_producer import VoiceEvaluateMessageProducer
from modules.voiceinterview.repository.evaluation_repository import VoiceInterviewEvaluationRepository
from modules.voiceinterview.repository.message_repository import VoiceInterviewMessageRepository
from modules.voiceinterview.repository.session_repository import VoiceInterviewSessionRepository
from modules.voiceinterview.realtime.manager import VoiceInterviewRuntimeManager
from modules.voiceinterview.router import rest_router as voice_rest_router_module
from modules.voiceinterview.router.websocket_router import configure_runtime_manager
from modules.voiceinterview.service.context_service import ContextMode, VoiceInterviewContextService
from modules.voiceinterview.service.conversation_service import VoiceInterviewConversationService
from modules.voiceinterview.service.evaluation_recovery_service import VoiceEvaluationRecoveryService
from modules.voiceinterview.service.evaluation_service import VoiceInterviewEvaluationService
from modules.voiceinterview.service.prompt_builder import VoiceInterviewPromptBuilder
from modules.voiceinterview.service.session_service import VoiceInterviewSessionService
from modules.voiceinterview.speech.dashscope import (
    DashScopeAsrConfig,
    DashScopeAsrProvider,
    DashScopeTtsConfig,
    DashScopeTtsProvider,
)

# ==================== Shared Infrastructure ====================

file_storage_service = FileStorageService()
file_hash_service = FileHashService()
document_parse_service = DocumentParseService()
file_validation_service = FileValidationService()

# ==================== Dynamic LLM Provider Center ====================

llm_provider_repository = LlmProviderRepository()
api_key_encryption_service = ApiKeyEncryptionService()
llm_provider_registry = LlmProviderRegistry(
    llm_provider_repository,
    api_key_encryption_service,
)
llm_provider_service = LlmProviderService(
    llm_provider_repository,
    api_key_encryption_service,
    llm_provider_registry,
)

# ==================== Interview Schedule Module ====================

interview_schedule_repository = InterviewScheduleRepository()
interview_schedule_service = InterviewScheduleService(interview_schedule_repository)
interview_parse_service = InterviewParseService(llm_provider_registry)
schedule_status_updater = ScheduleStatusUpdater(
    async_session_factory,
    interview_schedule_repository,
)

# ==================== Resume Module ====================

resume_repository = ResumeRepository()
interview_repository = InterviewRepository()
interview_persistence_service = InterviewPersistenceService(interview_repository)
interview_history_service = InterviewHistoryService(interview_repository)
interview_skill_service = InterviewSkillService(llm_provider_resolver=llm_provider_registry)
llm_provider_resolver = llm_provider_registry
interview_creation_coordinator = InterviewCreationCoordinator()
evaluate_message_producer = EvaluateMessageProducer(interview_repository)
interview_agent_service = InterviewAgentService(
    interview_repository,
    evaluate_message_producer,
    interview_skill_service,
    llm_provider_resolver,
    interview_creation_coordinator,
)
interview_evaluate_consumer_service = InterviewEvaluateConsumerService(interview_agent_service, interview_repository)
evaluate_message_consumer = EvaluateMessageConsumer(interview_evaluate_consumer_service, evaluate_message_producer)

analyze_message_producer = AnalyzeMessageProducer(resume_repository)
resume_grading_service = ResumeGradingService(llm_provider_registry)
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
knowledgebase_question_repository = KnowledgeBaseQuestionRepository()
rag_chat_repository = RagChatRepository()
rag_chat_session_repository = RagChatSessionRepository()
vector_service = MilvusVectorService(registry=llm_provider_registry)
knowledgebase_vector_service = KnowledgeBaseVectorService(vector_service)

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
knowledgebase_query_service = KnowledgeBaseQueryService(
    knowledgebase_list_service,
    knowledgebase_vector_service,
    knowledgebase_count_service,
    llm_provider_registry,
)
rag_chat_session_service = RagChatSessionService(rag_chat_session_repository, knowledgebase_query_service)

question_generation_state_service = QuestionGenerationStateService(
    knowledgebase_repository, knowledgebase_question_repository
)
question_generation_message_producer = QuestionGenerationMessageProducer(
    question_generation_state_service
)
knowledgebase_question_service = KnowledgeBaseQuestionService(
    knowledgebase_repository,
    knowledgebase_question_repository,
    question_generation_state_service,
    question_generation_message_producer,
)
knowledgebase_question_generation_service = KnowledgeBaseQuestionGenerationService(
    knowledgebase_repository,
    knowledgebase_question_repository,
    knowledgebase_vector_service,
    llm_provider_registry,
    question_generation_state_service,
)
question_generation_message_consumer = QuestionGenerationMessageConsumer(
    knowledgebase_question_generation_service,
    question_generation_state_service,
    question_generation_message_producer,
)
question_generation_recovery_service = QuestionGenerationRecoveryService(
    async_session_factory,
    knowledgebase_repository,
    question_generation_state_service,
    question_generation_message_producer,
)
knowledgebase_interview_service = KnowledgeBaseInterviewService(
    knowledgebase_repository, knowledgebase_question_repository, interview_agent_service
)

# ==================== Voice Interview Module ====================

voice_session_repository = VoiceInterviewSessionRepository()
voice_message_repository = VoiceInterviewMessageRepository()
voice_evaluation_repository = VoiceInterviewEvaluationRepository()
voice_evaluate_message_producer = VoiceEvaluateMessageProducer()

voice_interview_session_service = VoiceInterviewSessionService(
    voice_session_repository,
    voice_message_repository,
    voice_evaluation_repository,
    voice_evaluate_message_producer.send_evaluate_task_async,
    resume_repository,
    interview_skill_service,
    app_config.voice_evaluation_processing_stale_seconds,
)
voice_context_service = VoiceInterviewContextService(
    voice_message_repository,
    llm_provider_registry,
    ContextMode(app_config.voice_context_mode.upper()),
    app_config.voice_context_window_size,
    app_config.voice_context_summary_batch_size,
    app_config.voice_context_summary_timeout_seconds,
)
voice_prompt_builder = VoiceInterviewPromptBuilder(interview_skill_service)
voice_conversation_service = VoiceInterviewConversationService(
    voice_prompt_builder,
    voice_context_service,
    llm_provider_registry,
    resume_repository,
    voice_message_repository,
    app_config.voice_llm_timeout_seconds,
    app_config.voice_ai_question_max_chars,
)
voice_asr_provider = DashScopeAsrProvider(DashScopeAsrConfig(
    api_key=app_config.voice_dashscope_api_key,
    url=app_config.voice_dashscope_realtime_url,
    model=app_config.voice_asr_model,
    language=app_config.voice_asr_language,
    format=app_config.voice_asr_format,
    sample_rate=app_config.voice_asr_sample_rate,
    enable_turn_detection=app_config.voice_asr_enable_turn_detection,
    turn_detection_type=app_config.voice_asr_turn_detection_type,
    turn_detection_threshold=app_config.voice_asr_turn_detection_threshold,
    turn_detection_silence_duration_ms=app_config.voice_asr_turn_detection_silence_duration_ms,
    connect_timeout_seconds=app_config.voice_external_connect_timeout_seconds,
))
voice_tts_provider = DashScopeTtsProvider(DashScopeTtsConfig(
    api_key=app_config.voice_dashscope_api_key,
    url=app_config.voice_dashscope_realtime_url,
    model=app_config.voice_tts_model,
    voice=app_config.voice_tts_voice,
    format=app_config.voice_tts_format,
    sample_rate=app_config.voice_tts_sample_rate,
    mode=app_config.voice_tts_mode,
    language_type=app_config.voice_tts_language_type,
    speech_rate=app_config.voice_tts_speech_rate,
    volume=app_config.voice_tts_volume,
    connect_timeout_seconds=app_config.voice_external_connect_timeout_seconds,
    response_timeout_seconds=app_config.voice_tts_timeout_seconds,
))
voice_provider_config_repository = VoiceProviderConfigRepository()
voice_provider_config_service = VoiceProviderConfigService(
    voice_provider_config_repository,
    api_key_encryption_service,
    voice_asr_provider,
    voice_tts_provider,
)
voice_runtime_manager = VoiceInterviewRuntimeManager(
    session_service=voice_interview_session_service,
    conversation_service=voice_conversation_service,
    asr_provider=voice_asr_provider,
    tts_provider=voice_tts_provider,
    cooldown_ms=app_config.voice_echo_cooldown_ms,
    tts_concurrency=app_config.voice_max_concurrent_tts,
    max_asr_reconnects=app_config.voice_asr_max_reconnects,
)
configure_runtime_manager(voice_runtime_manager)
voice_rest_router_module.voice_interview_session_service = voice_interview_session_service
voice_rest_router_module.configure_runtime_manager(voice_runtime_manager)

voice_evaluation_service = VoiceInterviewEvaluationService(
    async_session_factory,
    voice_session_repository,
    voice_message_repository,
    voice_evaluation_repository,
    resume_repository,
    interview_agent_service.evaluation_agent_service,
    interview_skill_service,
)
voice_evaluate_message_consumer = VoiceEvaluateMessageConsumer(
    voice_evaluation_service, voice_evaluate_message_producer
)
voice_evaluation_recovery_service = VoiceEvaluationRecoveryService(
    async_session_factory,
    voice_session_repository,
    voice_evaluate_message_producer,
    app_config.voice_evaluation_recovery_interval_seconds,
    app_config.voice_evaluation_pending_stale_seconds,
    app_config.voice_evaluation_processing_stale_seconds,
)

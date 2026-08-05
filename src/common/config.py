from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfigProperties(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Dynamic LLM provider center. The encryption key is deliberately optional
    # during module import and is validated by the application lifespan.
    llm_provider_encryption_key: str | None = None
    llm_provider_bootstrap_json: str | None = None
    llm_default_chat_provider: str | None = None
    llm_default_embedding_provider: str | None = None
    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    allowed_types: List[str] = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown"
    ]
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB
    # RocketMQ config
    rocketmq_endpoints: str = "localhost:8081"
    rocketmq_producer_group: str = "resume-producer-group"
    rocketmq_consumer_group: str = "resume-consumer-group"
    rocketmq_max_retry_count: int = 3
    resume_analyze_topic: str = "resume-analyze-topic"
    resume_analyze_tag: str = "analyze"
    interview_evaluate_topic: str = "interview-evaluate-topic"
    interview_evaluate_tag: str = "evaluate"
    interview_evaluate_consumer_group: str = "interview-evaluate-consumer-group"
    voice_interview_evaluate_topic: str = "voice-interview-evaluate-topic"
    voice_interview_evaluate_tag: str = "evaluate"
    voice_interview_evaluate_consumer_group: str = "voice-interview-evaluate-consumer-group"
    database_url: str = "mysql+aiomysql://root:123@localhost:3308/interview"
    db_uri: str = "mysql+aiomysql://root:123@localhost:3308/checkpointer"

    # RustFS (S3 compatible) config
    rustfs_endpoint_url: str = "http://localhost:9000"
    rustfs_access_key: str = "rustfsadmin"
    rustfs_secret_key: str = "rustfsadmin"
    rustfs_region_name: str = "us-east-1"
    rustfs_bucket_name: str = "resources"

    # document parse config
    MAX_PARSE_TIME: float = 60.0 # 最大的文档解析时间是60s

    # Knowledge Base config
    kb_vectorize_topic: str = "kb-vectorize-topic"
    kb_vectorize_tag: str = "vectorize"
    kb_vectorize_consumer_group: str = "kb-vectorize-consumer-group"
    kb_question_gen_topic: str = "kb-question-gen-topic"
    kb_question_gen_tag: str = "generate"
    kb_question_gen_producer_group: str = "kb-question-gen-producer-group"
    kb_question_gen_consumer_group: str = "kb-question-gen-consumer-group"
    kb_allowed_types: list[str] = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
    ]
    kb_max_file_size_bytes: int = 50 * 1024 * 1024  # 50MB
    rustfs_kb_bucket_name: str = "knowledgebases"

    # Tokenizer
    tokenizer_name: str = "cl100k_base"

    # Voice interview. Missing credentials do not prevent application startup;
    # the WebSocket returns a configuration error when speech is requested.
    voice_dashscope_api_key: str | None = None
    voice_dashscope_realtime_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    voice_asr_model: str = "qwen3-asr-flash-realtime"
    voice_tts_model: str = "qwen3-tts-flash-realtime"
    voice_tts_voice: str = "Cherry"
    voice_asr_language: str = "zh"
    voice_asr_format: str = "pcm"
    voice_asr_sample_rate: int = 16000
    voice_asr_enable_turn_detection: bool = True
    voice_asr_turn_detection_type: str = "server_vad"
    voice_asr_turn_detection_threshold: float = 0.0
    voice_asr_turn_detection_silence_duration_ms: int = 1000
    voice_tts_format: str = "pcm"
    voice_tts_sample_rate: int = 24000
    voice_tts_mode: str = "commit"
    voice_tts_language_type: str = "Chinese"
    voice_tts_speech_rate: float = 1.0
    voice_tts_volume: int = 60
    voice_external_connect_timeout_seconds: float = 5.0
    voice_asr_ready_timeout_seconds: float = 10.0
    voice_tts_timeout_seconds: float = 8.0
    voice_llm_timeout_seconds: float = 30.0
    voice_asr_max_reconnects: int = 2
    voice_echo_cooldown_ms: int = 800
    voice_max_concurrent_tts: int = 3
    voice_ai_question_max_chars: int = 120
    voice_trust_forwarded_headers: bool = False
    voice_public_ws_base_url: str | None = None
    voice_allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    voice_context_mode: str = "SUMMARY"
    voice_context_window_size: int = 20
    voice_context_summary_batch_size: int = 10
    voice_context_summary_timeout_seconds: float = 20.0
    voice_evaluation_recovery_interval_seconds: int = 60
    voice_evaluation_pending_stale_seconds: int = 120
    voice_evaluation_processing_stale_seconds: int = 600

    # ElasticSearch
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_name: str = "smart_service"
    elasticsearch_query_mode: str = "dense_vector"

    # Knowledge-base runtime tuning (model credentials live in the provider DB).
    kb_embedding_batch_size: int = 10
    kb_short_query_length: int = 4
    kb_mid_query_length: int = 12
    kb_top_k_short: int = 20
    kb_top_k_medium: int = 12
    kb_top_k_long: int = 8
    kb_min_score_short: float = 0.18
    kb_min_score_default: float = 0.28

app_config = AppConfigProperties()

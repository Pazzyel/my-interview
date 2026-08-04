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
    database_url: str = "mysql+aiomysql://root:123@localhost:3308/interview"
    DB_URI: str = "mysql+aiomysql://root:123@localhost:3308/checkpointer" # 这是LangGraph checkpointer的保存点

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

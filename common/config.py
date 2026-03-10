from typing import List
from pydantic_settings import BaseSettings

class AppConfigProperties(BaseSettings):
    allowed_types: List[str] = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown"
    ]
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB
    # Kafka config
    kafka_bootstrap_servers: str = "localhost:9092"
    resume_analyze_topic: str = "resume-analyze-topic"
    resume_analyze_tag: str = "analyze"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/interview_db"

    # RustFS (S3 compatible) config
    rustfs_endpoint_url: str = "http://localhost:9000"
    rustfs_access_key: str = "minioadmin"
    rustfs_secret_key: str = "minioadmin"
    rustfs_region_name: str = "us-east-1"
    rustfs_bucket_name: str = "resumes"

    # document parse config
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 最大文件10MB
    MAX_PARSE_TIME: float = 60.0 # 最大的文档解析时间是60s

    class Config:
        env_file = ".env"

app_config = AppConfigProperties()

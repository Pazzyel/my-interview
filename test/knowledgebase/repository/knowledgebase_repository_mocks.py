"""
该模块提供 knowledgebase Repository 测试所需的辅助工具。

- InMemorySqliteSessionFactory: 复用 resume 模块的 SQLite 内存数据库工厂
- build_knowledgebase_entity: 构造测试用 KnowledgeBaseEntity
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
RESUME_REPO_TEST_ROOT = PROJECT_ROOT / "test" / "resume" / "repository"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(RESUME_REPO_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(RESUME_REPO_TEST_ROOT))

# 复用 resume 模块已有的 InMemorySqliteSessionFactory
from resume_repository_mocks import InMemorySqliteSessionFactory

from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus


def build_knowledgebase_entity(
    *,
    file_hash: str = "test-hash-default",
    name: str = "测试知识库",
    category: Optional[str] = "默认分类",
    original_filename: str = "test.pdf",
    file_size: int = 2048,
    content_type: str = "application/pdf",
    storage_key: Optional[str] = "kb/test.pdf",
    storage_url: Optional[str] = "https://example.test/test.pdf",
    uploaded_at: Optional[datetime] = None,
    vector_status: VectorStatus = VectorStatus.PENDING,
    vector_error: Optional[str] = None,
    access_count: int = 1,
    question_count: int = 0,
    chunk_count: int = 0,
) -> KnowledgeBaseEntity:
    """构造测试用 KnowledgeBaseEntity（替代业务层真实入参构造）。"""
    return KnowledgeBaseEntity(
        file_hash=file_hash,
        name=name,
        category=category,
        original_filename=original_filename,
        file_size=file_size,
        content_type=content_type,
        storage_key=storage_key,
        storage_url=storage_url,
        uploaded_at=uploaded_at or datetime.now(),
        last_accessed_at=uploaded_at or datetime.now(),
        access_count=access_count,
        question_count=question_count,
        vector_status=vector_status,
        vector_error=vector_error,
        chunk_count=chunk_count,
    )

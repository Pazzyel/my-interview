from typing import TypeAlias

from langchain_elasticsearch import AsyncElasticsearchStore, AsyncDenseVectorStrategy

from common.ai_config import ai_config
from common.config import app_config

VectorStore: TypeAlias = AsyncElasticsearchStore


vector_store: VectorStore = AsyncElasticsearchStore(
    es_url=app_config.elasticsearch_url,
    index_name=app_config.elasticsearch_index_name,
    embedding=ai_config.embeddings,
    strategy=AsyncDenseVectorStrategy(),
)

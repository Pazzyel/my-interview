from typing import TypeAlias

from langchain_elasticsearch import AsyncDenseVectorStrategy, AsyncElasticsearchStore
from langchain_openai import OpenAIEmbeddings

from common.config import app_config

VectorStore: TypeAlias = AsyncElasticsearchStore


def create_vector_store(embedding: OpenAIEmbeddings) -> VectorStore:
    return AsyncElasticsearchStore(
        es_url=app_config.elasticsearch_url,
        index_name=app_config.elasticsearch_index_name,
        embedding=embedding,
        strategy=AsyncDenseVectorStrategy(),
    )

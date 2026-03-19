from langchain_elasticsearch import ElasticsearchStore, DenseVectorStrategy

from common.ai_config import ai_config
from common.config import app_config

vector_store = ElasticsearchStore(
    es_url=app_config.elasticsearch_url,
    index_name=app_config.elasticsearch_index_name,
    embedding=ai_config.embeddings,
    strategy=DenseVectorStrategy(),
)

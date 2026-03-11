import os

from langchain_community.embeddings import OpenAIEmbeddings


class AIConfigProperties:
    embeddings_model_name: str = "text-embedding-3-small"
    embeddings = OpenAIEmbeddings(
        model=embeddings_model_name,
        api_key=os.environ["OPENAI_API_KEY"],
    )
    # 嵌入模型 API 批量大小限制
    MAX_BATCH_SIZE = 10

ai_config = AIConfigProperties()
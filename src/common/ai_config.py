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

    chat_model_name: str = "gpt-4o"
    chat_api_key = os.environ["OPENAI_API_KEY"]
    base_url = "https://api.openai.com/v1"

    short_query_length = 4
    mid_query_length = 12
    top_k_short = 20
    top_k_medium = 12
    top_k_long = 8

    min_score_shot = 0.18
    min_score_default = 0.28

ai_config = AIConfigProperties()
import os

from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr


class AIConfigProperties:
    embeddings_model_name: str = "text-embedding-v4"
    embeddings = OpenAIEmbeddings(
        model=embeddings_model_name,
        api_key=SecretStr(os.environ["DASHSCOPE_API_KEY"]),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        check_embedding_ctx_length=False,  # 关闭上下文长度检查，防止输入被修改为非字符串
    )
    # 嵌入模型 API 批量大小限制
    MAX_BATCH_SIZE = 10

    chat_model_name: str = "GLM-5"
    chat_api_key: str = os.environ["OPENAI_API_KEY"]
    base_url: str = "https://api.edgefn.net/v1"

    short_query_length: int = 4
    mid_query_length: int = 12
    top_k_short: int = 20
    top_k_medium: int = 12
    top_k_long: int = 8

    min_score_short: float = 0.18
    min_score_default: float = 0.28

ai_config = AIConfigProperties()
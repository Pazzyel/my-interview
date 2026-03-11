import os

from langchain_community.embeddings import OpenAIEmbeddings


class AIConfigProperties:
    embeddings_model_name: str = "text-embedding-3-small"
    embeddings = OpenAIEmbeddings(
        model=embeddings_model_name,
        api_key=os.environ["OPENAI_API_KEY"],
    )

ai_config = AIConfigProperties()
from typing import Protocol

from langchain_openai import ChatOpenAI


class LlmProviderResolver(Protocol):
    """Resolve a chat model for a persisted provider identifier."""

    def resolve(self, provider: str | None) -> ChatOpenAI:
        ...


class AiConfigLlmProviderResolver:
    """Current single-provider implementation backed by common.ai_config."""

    def __init__(self) -> None:
        self._chat_model: ChatOpenAI | None = None

    def resolve(self, provider: str | None) -> ChatOpenAI:
        # TODO(multi-provider): Replace this single cached model with a provider registry.
        # The registry should resolve model name, API key and base URL by `provider`.
        # Interview services already pass the persisted provider value through this
        # interface, so no business-flow changes should be needed at that time.
        _ = provider
        if self._chat_model is None:
            from pydantic import SecretStr

            from common.ai_config import ai_config

            self._chat_model = ChatOpenAI(
                model=ai_config.chat_model_name,
                api_key=SecretStr(ai_config.chat_api_key),
                base_url=ai_config.base_url,
                temperature=0,
            )
        return self._chat_model

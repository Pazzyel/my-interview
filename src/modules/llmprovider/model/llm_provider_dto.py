import re

from pydantic import Field, SecretStr, field_validator, model_validator

from infrastructure.model.BaseCamelSchema import BaseCamelSchema


PROVIDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ProviderFields(BaseCamelSchema):
    base_url: str
    model: str
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    supports_embedding: bool = False
    temperature: float = Field(default=0, ge=0, le=2)
    enabled: bool = True

    @field_validator("base_url", "model")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_embedding(self):
        if self.supports_embedding:
            if not self.embedding_model or not self.embedding_model.strip():
                raise ValueError("embeddingModel is required when supportsEmbedding=true")
            if not self.embedding_dimensions or self.embedding_dimensions <= 0:
                raise ValueError("embeddingDimensions must be positive when supportsEmbedding=true")
        return self


class LlmProviderCreateRequest(ProviderFields):
    id: str
    api_key: SecretStr

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not PROVIDER_ID_PATTERN.fullmatch(value):
            raise ValueError("id must contain only letters, numbers, underscores or hyphens")
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def valid_api_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("apiKey must not be blank")
        return value.strip()


class LlmProviderUpdateRequest(BaseCamelSchema):
    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    supports_embedding: bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    enabled: bool | None = None


class LlmProviderDTO(BaseCamelSchema):
    id: str
    base_url: str
    masked_api_key: str
    model: str
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    supports_embedding: bool
    temperature: float
    enabled: bool
    builtin: bool
    default_chat_provider: bool = False
    default_embedding_provider: bool = False


class DefaultProviderDTO(BaseCamelSchema):
    default_provider: str
    default_embedding_provider: str


class ProviderTestResultDTO(BaseCamelSchema):
    success: bool
    message: str
    model: str

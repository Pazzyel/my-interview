"""Compatibility import for the database-backed model registry."""

from modules.llmprovider.service.llm_provider_registry import (
    LlmProviderRegistry,
    LlmProviderResolver,
)

__all__ = ["LlmProviderRegistry", "LlmProviderResolver"]

"""Model registry: name -> LLM provider configuration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..errors import DuplicateNameError, RegistryKeyError

_REGISTRY_NAME = "ModelRegistry"


class ModelConfig(BaseModel):
    provider_name: str
    model_id: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}

    def register(self, name: str, config: ModelConfig) -> None:
        if name in self._models:
            raise DuplicateNameError(_REGISTRY_NAME, name)
        self._models[name] = config

    def get(self, name: str) -> ModelConfig:
        if name not in self._models:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        return self._models[name]

    def list(self) -> list[str]:
        return list(self._models.keys())

    def update(self, name: str, config: ModelConfig) -> None:
        if name not in self._models:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        self._models[name] = config

    def delete(self, name: str) -> None:
        if name not in self._models:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        del self._models[name]

    def has(self, name: str) -> bool:
        return name in self._models

"""Single source of truth for available LLM models."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

ModelStatus = Literal["active", "preview", "deprecated"]


@dataclass
class ModelEntry:
    id: str          # 送信用ID (例: "gemini-2.5-pro" or "openai:gpt-4.1")
    name: str        # 表示名
    provider: str    # "gemini" | "openai" | "anthropic"
    status: ModelStatus = "active"
    priority: int = 0  # UIソート用 (小さいほど上位)


@dataclass
class ModelGroup:
    group: str       # 表示グループ名
    provider: str
    models: list[ModelEntry] = field(default_factory=list)


# --- カタログ定義 ---
CATALOG: list[ModelGroup] = [
    ModelGroup(group="Gemini", provider="gemini", models=[
        ModelEntry("gemini-3.1-pro-preview", "Gemini 3.1 Pro",   "gemini", priority=0),
        ModelEntry("gemini-3-flash-preview", "Gemini 3 Flash",   "gemini", priority=1),
        ModelEntry("gemini-2.5-pro",         "Gemini 2.5 Pro",   "gemini", priority=2),
        ModelEntry("gemini-2.5-flash",       "Gemini 2.5 Flash", "gemini", priority=3),
    ]),
    ModelGroup(group="OpenAI", provider="openai", models=[
        ModelEntry("openai:gpt-5",        "GPT-5",               "openai", priority=0),
        ModelEntry("openai:gpt-5-mini",   "GPT-5 Mini",          "openai", priority=1),
        ModelEntry("openai:gpt-5-nano",   "GPT-5 Nano",          "openai", priority=2),
        ModelEntry("openai:gpt-4.1",      "GPT-4.1",             "openai", priority=3),
        ModelEntry("openai:gpt-4.1-mini", "GPT-4.1 Mini",        "openai", priority=4),
        ModelEntry("openai:o4-mini",      "o4 Mini (reasoning)", "openai", priority=5),
        ModelEntry("openai:o3",           "o3 (reasoning)",      "openai", priority=6),
    ]),
    ModelGroup(group="Claude", provider="anthropic", models=[
        ModelEntry("anthropic:claude-opus-4-6-20260220", "Claude Opus 4.6",  "anthropic", priority=0),
        ModelEntry("anthropic:claude-opus-4-5-20251101", "Claude Opus 4.5",  "anthropic", priority=1),
        ModelEntry("anthropic:claude-sonnet-4-20250514", "Claude Sonnet 4",  "anthropic", priority=2),
        ModelEntry("anthropic:claude-haiku-4-5",         "Claude Haiku 4.5", "anthropic", priority=3),
    ]),
]

DEFAULT_MODEL = "gemini-3-pro-preview"

# 全モデルIDセット (バリデーション用)
_ALL_MODEL_IDS: set[str] = {m.id for g in CATALOG for m in g.models}


def is_valid_model(model_id: str) -> bool:
    return model_id in _ALL_MODEL_IDS


def resolve_model(model_id: str | None) -> str:
    """不明・None のモデルはデフォルトに解決する。"""
    if model_id and is_valid_model(model_id):
        return model_id
    return DEFAULT_MODEL


def catalog_to_dict() -> dict:
    return {
        "default_model": DEFAULT_MODEL,
        "groups": [
            {
                "group": g.group,
                "provider": g.provider,
                "models": [
                    {"id": m.id, "name": m.name, "status": m.status, "priority": m.priority}
                    for m in sorted(g.models, key=lambda x: x.priority)
                    if m.status != "deprecated"
                ],
            }
            for g in CATALOG
        ],
    }

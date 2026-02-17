"""Backward-compat re-export — ToolDispatcher now lives in engine/registry/."""

from ..engine.registry.tool_dispatcher import (  # noqa: F401
    EngineToolAdapter,
    ToolDispatcher,
)

__all__ = ["EngineToolAdapter", "ToolDispatcher"]

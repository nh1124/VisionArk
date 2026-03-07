"""Codex integration — service config helper."""

from __future__ import annotations

SERVICE_NAME = "codex"


async def get_codex_config(user_id: str, db) -> dict | None:
    """Return service config dict if codex is active for this user, else None."""
    from sqlalchemy import select
    from shared.database import ServiceRegistry

    res = await db.execute(
        select(ServiceRegistry).where(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name == SERVICE_NAME,
            ServiceRegistry.is_active == True,  # noqa: E712
        )
    )
    svc = res.scalars().first()
    if not svc:
        return None

    cfg = svc.config or {}
    return {
        "api_key": svc.api_key,  # decrypted via property
        "base_url": svc.base_url,
        "default_device_id": cfg.get("default_device_id"),
        "default_timeout_sec": int(cfg.get("default_timeout_sec", 120)),
        "allowed_workdirs": cfg.get("allowed_workdirs", []),
        "profile": cfg.get("profile", "standard"),
    }

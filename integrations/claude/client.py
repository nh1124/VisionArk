"""Claude CLI integration — service config helper."""

from __future__ import annotations

SERVICE_NAME = "claude"


async def get_claude_config(user_id: str, db) -> dict | None:
    """Return service config dict if claude CLI is active for this user, else None."""
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
        "api_key": svc.api_key,
        "base_url": svc.base_url,
        "default_device_id": cfg.get("default_device_id"),
        "default_timeout_sec": int(cfg.get("default_timeout_sec", 300)),
        "allowed_workdirs": cfg.get("allowed_workdirs", []),
        "default_model": cfg.get("default_model", ""),
        "profile": cfg.get("profile", "standard"),
    }

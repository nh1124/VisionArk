"""Native device & job agent tools for VisionArk.

Tools
-----
ListNativeDevicesTool   List the user's registered native devices with status/capability info.
RunNativeJobTool        Create a job targeted at a specific device (or auto-routed).
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from pydantic import Field
from va_sdk import BaseTool, BaseModel, IntegrationContext, ToolResult

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ok(data: Any) -> ToolResult:
    return ToolResult(content=json.dumps(data, ensure_ascii=False), data=data, is_success=True)


def _err(message: str) -> ToolResult:
    return ToolResult(content=message, is_success=False)


async def _api(ctx: IntegrationContext, method: str, path: str, body: Optional[dict] = None):
    """Minimal async HTTP helper using the backend's internal session."""
    import httpx
    from app.config import settings  # noqa: WPS433

    base_url = getattr(settings, "internal_api_url", "http://localhost:8000")
    headers = {
        "Content-Type": "application/json",
        "X-Internal-User-Id": ctx.user_id,
    }
    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        kwargs: dict = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        resp = await client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# list_native_devices
# ═══════════════════════════════════════════════════════════════════════════════

class ListNativeDevicesArgs(BaseModel):
    enabled_only: bool = Field(False, description="If true, return only enabled devices.")
    online_only: bool = Field(False, description="If true, return only online devices.")
    capability: Optional[str] = Field(
        None,
        description="Filter devices that have this capability (e.g. 'run_shell', 'file_rw').",
    )


class ListNativeDevicesTool(BaseTool):
    name = "list_native_devices"
    description = (
        "List the user's registered native devices (desktops, servers, mobiles). "
        "Returns device_id, display_name, platform, status, is_enabled, and capabilities for each device. "
        "Use this tool before run_native_job to choose the target_device_id."
    )
    args_schema = ListNativeDevicesArgs

    async def run(
        self,
        ctx: IntegrationContext = None,
        enabled_only: bool = False,
        online_only: bool = False,
        capability: Optional[str] = None,
        **kwargs,
    ) -> Any:
        if not ctx:
            return _err("Context is required")
        try:
            from sqlalchemy import select
            from shared.database import NativeDevice

            db = ctx.db
            stmt = select(NativeDevice).where(NativeDevice.user_id == ctx.user_id)
            result = await db.execute(stmt)
            devices = result.scalars().all()

            data = []
            for d in devices:
                if enabled_only and not d.is_enabled:
                    continue
                if online_only and d.status != "online":
                    continue
                caps: List[str] = d.capabilities or []
                if capability and capability not in caps:
                    continue
                data.append({
                    "device_id": d.id,
                    "display_name": d.display_name,
                    "device_kind": d.device_kind,
                    "platform": d.platform,
                    "client_version": d.client_version,
                    "capabilities": caps,
                    "is_enabled": d.is_enabled,
                    "status": d.status,
                    "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
                })

            summary = (
                f"{len(data)} device(s) found"
                + (f" (enabled_only={enabled_only}" if enabled_only else "")
                + (f", online_only={online_only}" if online_only else "")
                + (f", capability={capability}" if capability else "")
                + (")" if enabled_only or online_only or capability else "")
            )
            return _ok({"devices": data, "count": len(data), "summary": summary})

        except Exception as exc:
            logger.exception("list_native_devices failed: %s", exc)
            return _err(f"Failed to list devices: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# run_native_job
# ═══════════════════════════════════════════════════════════════════════════════

class RunNativeJobArgs(BaseModel):
    job_type: str = Field(
        ...,
        description=(
            "Job type identifier. Known prefixes: local.dev, local.file, local.app, "
            "integration.email, integration.ec. Can be any descriptive string."
        ),
    )
    payload: dict = Field(
        default_factory=dict,
        description="Arbitrary job payload passed to the daemon executor.",
    )
    target_device_id: Optional[str] = Field(
        None,
        description=(
            "Device ID obtained from list_native_devices. "
            "If omitted, routing_mode defaults to 'auto' and the backend selects the best available device."
        ),
    )
    risk_level: str = Field(
        "low",
        description="Risk level: low | medium | high | critical. High/critical steps require user approval.",
    )
    tags: List[str] = Field(default_factory=list, description="Optional tags for filtering.")


class RunNativeJobTool(BaseTool):
    name = "run_native_job"
    description = (
        "Create a native job to be executed on a user's device (desktop, server, or mobile). "
        "First call list_native_devices to find an appropriate device_id. "
        "The daemon on the target device will pick up the job, generate an execution plan, "
        "and run each step (subject to user approval for high-risk steps). "
        "Returns the created job object including job_id and status."
    )
    args_schema = RunNativeJobArgs

    async def run(
        self,
        ctx: IntegrationContext = None,
        job_type: str = "",
        payload: dict = None,
        target_device_id: Optional[str] = None,
        risk_level: str = "low",
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> Any:
        if not ctx:
            return _err("Context is required")
        if not job_type.strip():
            return _err("job_type is required")

        try:
            from sqlalchemy import select
            from shared.database import Job, NativeDevice, JobStatus
            import uuid
            from datetime import datetime

            db = ctx.db
            device_snapshot = None

            # Validate target device if specified
            if target_device_id:
                res = await db.execute(
                    select(NativeDevice).where(
                        NativeDevice.id == target_device_id,
                        NativeDevice.user_id == ctx.user_id,
                    )
                )
                device = res.scalars().first()
                if not device:
                    return _err(f"Device '{target_device_id}' not found or not owned by this user.")
                if not device.is_enabled:
                    return _err(
                        f"Device '{device.display_name}' is not enabled. "
                        "Enable it in Settings > Devices before using it as a target."
                    )
                device_snapshot = {
                    "id": device.id,
                    "display_name": device.display_name,
                    "device_kind": device.device_kind,
                    "platform": device.platform,
                    "status": device.status,
                }

            routing_mode = "manual" if target_device_id else "auto"
            job = Job(
                id=str(uuid.uuid4()),
                user_id=ctx.user_id,
                project_id=ctx.project_id,
                source="agent",
                type=job_type.strip(),
                tags=tags or [],
                status=JobStatus.QUEUED,
                risk_level=risk_level,
                payload=payload or {},
                target_device_id=target_device_id,
                routing_mode=routing_mode,
                device_snapshot=device_snapshot,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            logger.info(
                "run_native_job: user=%s job=%s type=%s device=%s routing=%s",
                ctx.user_id, job.id, job_type, target_device_id, routing_mode,
            )

            device_label = (
                device_snapshot["display_name"] if device_snapshot else "auto-selected device"
            )
            return _ok({
                "job_id": job.id,
                "status": job.status,
                "type": job.type,
                "target_device_id": job.target_device_id,
                "routing_mode": job.routing_mode,
                "risk_level": job.risk_level,
                "message": (
                    f"Job '{job_type}' queued for {device_label}. "
                    f"Monitor progress in Job Center (id={job.id})."
                ),
            })

        except Exception as exc:
            logger.exception("run_native_job failed: %s", exc)
            return _err(f"Failed to create job: {exc}")

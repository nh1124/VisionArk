"""Definition refresh service.

Collects tool/skill definitions from all sources (core static config + integrations)
and upserts them into the DB registries so that the engine can use DB as the
single source of truth.

Sources:
  core        — default_catalog.get_core_tools() + default_skills.SKILL_DEFS
  integration — integrations/* get_tools() + get_skill_defs()

Phases:
  Sync API  (refresh_core_sync)      — used by seed.py at user creation time
  Async API (refresh_all / refresh_integrations) — used by the /api/definitions/refresh endpoint
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _version_hash(data: Any) -> str:
    """Return first 16 hex chars of SHA-256 of the JSON-serialised data."""
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Sync core refresh — called from seed.py via synchronous Engine
# ---------------------------------------------------------------------------

def refresh_core_sync(engine: Engine, user_id: str) -> None:
    """Refresh core tools and skills from static config into DB (sync version)."""
    _refresh_core_tools_sync(engine, user_id)
    _refresh_core_skills_sync(engine, user_id)


def _refresh_core_tools_sync(engine: Engine, user_id: str) -> None:
    """Upsert all core tool definitions into tool_registry."""
    try:
        from domains.orchestration2.config.tools.default_catalog import get_core_tools
        tools = get_core_tools()
    except Exception as exc:
        logger.warning("Core tool refresh skipped — could not load default_catalog: %s", exc)
        return

    now = datetime.utcnow()
    with engine.begin() as conn:
        for tool_def, _ in tools:
            vh = _version_hash({"name": tool_def.name, "description": tool_def.description})
            conn.execute(
                text("""
                    INSERT INTO tool_registry
                        (id, user_id, name, description, params_schema,
                         origin_type, origin_id, status, is_active,
                         version_hash, activated_at, created_at, updated_at)
                    VALUES
                        (:id, :user_id, :name, :description,
                         CAST(:params_schema AS JSON),
                         'core', NULL, 'active', TRUE,
                         :vh, :now, :now, :now)
                    ON CONFLICT (user_id, name) DO UPDATE SET
                        description  = EXCLUDED.description,
                        params_schema = EXCLUDED.params_schema,
                        origin_type  = 'core',
                        status       = 'active',
                        is_active    = TRUE,
                        version_hash = EXCLUDED.version_hash,
                        updated_at   = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "name": tool_def.name,
                    "description": tool_def.description or "",
                    "params_schema": json.dumps({}),
                    "vh": vh,
                    "now": now,
                },
            )

    logger.info("✅ Refreshed %d core tools into tool_registry for user %s", len(tools), user_id)


def _refresh_core_skills_sync(engine: Engine, user_id: str) -> None:
    """Upsert all core skill definitions into skill_registry."""
    try:
        from domains.orchestration2.config.skills.default_skills import SKILL_DEFS
    except Exception as exc:
        logger.warning("Core skill refresh skipped — could not import SKILL_DEFS: %s", exc)
        return

    now = datetime.utcnow()
    new_names = [skill.name for skill in SKILL_DEFS]
    with engine.begin() as conn:
        for skill in SKILL_DEFS:
            vh = _version_hash({"name": skill.name, "tools": skill.tools, "instructions": skill.instructions})
            conn.execute(
                text("""
                    INSERT INTO skill_registry
                        (id, user_id, name, description, tools, instructions, is_builtin,
                         origin_type, origin_id, status, is_active,
                         version_hash, activated_at, created_at, updated_at)
                    VALUES
                        (:id, :user_id, :name, :description,
                         CAST(:tools AS JSON), :instructions, TRUE,
                         'core', NULL, 'active', TRUE,
                         :vh, :now, :now, :now)
                    ON CONFLICT (user_id, name) DO UPDATE SET
                        description  = EXCLUDED.description,
                        tools        = EXCLUDED.tools,
                        instructions = EXCLUDED.instructions,
                        origin_type  = 'core',
                        status       = 'active',
                        is_active    = TRUE,
                        version_hash = EXCLUDED.version_hash,
                        updated_at   = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "name": skill.name,
                    "description": skill.description or "",
                    "tools": json.dumps(skill.tools),
                    "instructions": skill.instructions,
                    "vh": vh,
                    "now": now,
                },
            )

        # Deactivate old builtin skills that are no longer in the current SKILL_DEFS
        if new_names:
            placeholders = ", ".join(f":name_{i}" for i in range(len(new_names)))
            params: dict = {"user_id": user_id, "now": now}
            params.update({f"name_{i}": n for i, n in enumerate(new_names)})
            conn.execute(
                text(f"""
                    UPDATE skill_registry SET is_active=FALSE, updated_at=:now
                    WHERE user_id=:user_id AND is_builtin=TRUE AND name NOT IN ({placeholders})
                """),
                params,
            )

    logger.info("✅ Refreshed %d core skills into skill_registry for user %s", len(SKILL_DEFS), user_id)


# ---------------------------------------------------------------------------
# Async integration refresh — called from the API endpoint
# ---------------------------------------------------------------------------

async def refresh_all(user_id: str, db: AsyncSession) -> dict:
    """Refresh core + integration definitions. Returns a summary dict."""
    import asyncio
    from shared.database import get_engine

    engine = get_engine()
    await asyncio.to_thread(refresh_core_sync, engine, user_id)
    integration_result = await refresh_integrations(user_id, db)
    return {
        "core_refreshed": True,
        "integration_tools": integration_result["tools"],
        "integration_skills": integration_result["skills"],
        "errors": integration_result.get("errors", []),
    }


async def refresh_integrations(user_id: str, db: AsyncSession) -> dict:
    """Refresh integration tools and skills into DB.

    After upserting tools and skills, updates the 'operation' skill in DB so
    that integration tools not assigned to any dedicated skill are included.
    This replaces the per-request runtime append that was previously done in
    tool_reflection.py.
    """
    from integrations.loader import load_integration_tools, load_integration_skills

    tools_count = 0
    skills_count = 0
    errors: list[str] = []

    tools: list = []
    skill_entries: list = []

    # --- Integration tools ---
    try:
        tools = await load_integration_tools(user_id, db)
        tools_count = await _upsert_tools_async(db, user_id, tools, origin_type="integration")
    except Exception as exc:
        msg = f"Integration tool refresh failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    # --- Integration skills ---
    try:
        skill_entries = await load_integration_skills(user_id, db)
        _, active_registered = await _get_service_registry_status(db, user_id)
        # Integrations are active only when explicitly enabled in ServiceRegistry.
        # LBS is a mandatory system integration, so its skill must stay active.
        active_services = set(active_registered)
        active_services.add("lbs")
        skills_count = await _upsert_skills_async(
            db, user_id, skill_entries, origin_type="integration",
            active_services=active_services,
        )
    except Exception as exc:
        msg = f"Integration skill refresh failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    # --- Update 'external_comms' skill with unassigned integration tools ---
    # Tools that belong to a dedicated integration skill (e.g. ms_office) are excluded.
    # All other integration tools are added to the 'external_comms' skill in DB,
    # replacing the per-request dynamic injection that was done in tool_reflection.py.
    try:
        await _update_external_comms_skill(db, user_id, tools, skill_entries)
    except Exception as exc:
        msg = f"External comms skill update failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    await db.commit()
    logger.info(
        "Integration refresh done for user %s: %d tools, %d skills",
        user_id, tools_count, skills_count,
    )
    return {"tools": tools_count, "skills": skills_count, "errors": errors}


async def _update_external_comms_skill(
    db: AsyncSession,
    user_id: str,
    integration_tools: list,      # list of (ToolDef, impl) from active integrations
    integration_skill_entries: list,  # list of (SkillDef, origin_id)
) -> None:
    """Recompute the 'external_comms' skill's tool list and persist to DB.

    The new list = integration tools not covered by any dedicated integration skill.
    This is recomputed from scratch on each refresh so that deactivated integrations
    are automatically removed.
    """
    # Tools already assigned to a dedicated integration skill
    covered: set[str] = set()
    for skill_def, _ in integration_skill_entries:
        covered.update(skill_def.tools)

    # Integration tools NOT covered by any dedicated skill
    uncovered = [td.name for td, _ in integration_tools if td.name not in covered]

    now = datetime.utcnow()
    vh = _version_hash({"name": "external_comms", "tools": uncovered})
    await db.execute(
        text("""
            UPDATE skill_registry
            SET tools        = CAST(:tools AS JSON),
                version_hash = :vh,
                updated_at   = :now
            WHERE user_id = :user_id AND name = 'external_comms'
        """),
        {
            "tools": json.dumps(uncovered),
            "vh": vh,
            "now": now,
            "user_id": user_id,
        },
    )
    logger.debug(
        "Updated external_comms skill for user %s: %d uncovered integration tools",
        user_id, len(uncovered),
    )


async def _get_service_registry_status(
    db: AsyncSession, user_id: str
) -> tuple[set[str], set[str]]:
    """Return (all_registered, active_registered) service name sets for this user.

    all_registered  — every service_name with any row in service_registry
    active_registered — service names where is_active=True
    """
    rows = await db.execute(
        text("SELECT service_name, is_active FROM service_registry WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    all_rows = rows.fetchall()
    all_registered = {r[0] for r in all_rows}
    active_registered = {r[0] for r in all_rows if r[1]}
    return all_registered, active_registered


async def _upsert_tools_async(
    db: AsyncSession,
    user_id: str,
    tools: list,  # list of (ToolDef, impl)
    origin_type: str = "core",
    origin_id: str | None = None,
) -> int:
    now = datetime.utcnow()
    count = 0
    for tool_def, _ in tools:
        origin_id_val = origin_id or getattr(tool_def, "origin_id", None)
        vh = _version_hash({"name": tool_def.name, "description": tool_def.description})
        await db.execute(
            text("""
                INSERT INTO tool_registry
                    (id, user_id, name, description, params_schema,
                     origin_type, origin_id, status, is_active,
                     version_hash, activated_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :name, :description,
                     CAST(:params_schema AS JSON),
                     :origin_type, :origin_id, 'active', TRUE,
                     :vh, :now, :now, :now)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    description  = EXCLUDED.description,
                    params_schema = EXCLUDED.params_schema,
                    origin_type  = EXCLUDED.origin_type,
                    origin_id    = EXCLUDED.origin_id,
                    status       = 'active',
                    is_active    = TRUE,
                    version_hash = EXCLUDED.version_hash,
                    updated_at   = EXCLUDED.updated_at
            """),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": tool_def.name,
                "description": tool_def.description or "",
                "params_schema": json.dumps({}),
                "origin_type": origin_type,
                "origin_id": origin_id_val,
                "vh": vh,
                "now": now,
            },
        )
        count += 1
    return count


async def _upsert_skills_async(
    db: AsyncSession,
    user_id: str,
    skill_entries: list,  # list of (SkillDef, origin_id_str)
    origin_type: str = "core",
    active_services: set[str] | None = None,
) -> int:
    """Upsert skills into skill_registry.

    When active_services is provided (for integration skills), is_active is set to:
      - True  if origin_id IS in active_services (service is active)
      - True  if origin_id == "lbs" (mandatory integration)
      - False otherwise (missing row or explicitly inactive)
    Core skills always get is_active=True (active_services=None).
    """
    now = datetime.utcnow()
    count = 0
    for skill_def, origin_id in skill_entries:
        # Determine active state for this skill
        if active_services is None:
            # Core skills: always active
            is_active = True
        else:
            is_active = (origin_id in active_services) or (origin_id == "lbs")

        vh = _version_hash({"name": skill_def.name, "tools": skill_def.tools, "instructions": getattr(skill_def, "instructions", None)})
        await db.execute(
            text("""
                INSERT INTO skill_registry
                    (id, user_id, name, description, tools, instructions, is_builtin,
                     origin_type, origin_id, status, is_active,
                     version_hash, activated_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :name, :description,
                     CAST(:tools AS JSON), :instructions, FALSE,
                     :origin_type, :origin_id, 'active', :is_active,
                     :vh, :now, :now, :now)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    description  = EXCLUDED.description,
                    tools        = EXCLUDED.tools,
                    instructions = EXCLUDED.instructions,
                    origin_type  = EXCLUDED.origin_type,
                    origin_id    = EXCLUDED.origin_id,
                    status       = 'active',
                    is_active    = EXCLUDED.is_active,
                    version_hash = EXCLUDED.version_hash,
                    updated_at   = EXCLUDED.updated_at
            """),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": skill_def.name,
                "description": skill_def.description or "",
                "tools": json.dumps(skill_def.tools),
                "instructions": getattr(skill_def, "instructions", None),
                "origin_type": origin_type,
                "origin_id": origin_id,
                "is_active": is_active,
                "vh": vh,
                "now": now,
            },
        )
        count += 1
    return count

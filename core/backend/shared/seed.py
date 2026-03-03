"""
Per-user skill / graph / agent seeder.
Called once at user creation time (auth.py) — NOT at server startup.
Idempotent: skills/graphs use ON CONFLICT DO UPDATE; agents use WHERE NOT EXISTS.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_GRAPHS_DIR = (
    Path(__file__).parent.parent
    / "domains"
    / "orchestration2"
    / "config"
    / "graphs"
)


# ---------------------------------------------------------------------------
# Delegation sub-agent definitions
# ---------------------------------------------------------------------------
# These agents are seeded once per user and loaded from DB at runtime.
# display_name is used as the engine agent name (must match delegate_task calls).
# NOTE: delegation skill is intentionally excluded to prevent recursive loops.
_SUB_AGENT_DEFS: list[dict] = [
    {
        "display_name": "researcher",
        "description": "Delegation sub-agent: research & investigation tasks",
        "skill_ids": ["research"],
        "graph_id": "direct_assistant",
    },
    {
        "display_name": "writer",
        "description": "Delegation sub-agent: document creation & writing tasks",
        "skill_ids": ["research", "authoring"],
        "graph_id": "direct_assistant",
    },
    {
        "display_name": "reviewer",
        "description": "Delegation sub-agent: research & review tasks",
        "skill_ids": ["research"],
        "graph_id": "direct_assistant",
    },
]


def seed_user_definitions(engine: Engine, user_id: str) -> None:
    """Seed tool_registry, skill_registry, graph_registry, and delegation agents for a user.

    Creates one row per tool/skill/graph per user.  Safe to re-run (upsert).
    """
    # Use the refresh service so DB columns (origin_type, status, is_active, etc.) are set correctly.
    try:
        from domains.orchestration2.bootstrap.definition_refresh_service import refresh_core_sync
        refresh_core_sync(engine, user_id)
    except Exception as exc:
        logger.warning("definition_refresh_service unavailable, falling back to legacy skill seed: %s", exc)
        _seed_skills(engine, user_id)
    _seed_graphs(engine, user_id)
    _seed_agents(engine, user_id)


def seed_user_agents(engine: Engine, user_id: str) -> None:
    """Seed only the delegation sub-agents for a user (lazy-seed entry point)."""
    _seed_agents(engine, user_id)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def _seed_skills(engine: Engine, user_id: str) -> None:
    try:
        from domains.orchestration2.config.skills.default_skills import SKILL_DEFS
    except ImportError as exc:
        logger.warning("Skill seeding skipped — could not import SKILL_DEFS: %s", exc)
        return

    now = datetime.utcnow()
    with engine.begin() as conn:
        for skill in SKILL_DEFS:
            conn.execute(
                text("""
                    INSERT INTO skill_registry
                        (id, user_id, name, description, tools, is_builtin, created_at, updated_at)
                    VALUES
                        (:id, :user_id, :name, :description, CAST(:tools AS JSON),
                         :is_builtin, :created_at, :updated_at)
                    ON CONFLICT (user_id, name) DO UPDATE SET
                        description = EXCLUDED.description,
                        tools       = EXCLUDED.tools,
                        updated_at  = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "name": skill.name,
                    "description": skill.description or "",
                    "tools": json.dumps(skill.tools),
                    "is_builtin": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    logger.info("✅ Seeded %d skills into skill_registry for user %s", len(SKILL_DEFS), user_id)


# ---------------------------------------------------------------------------
# Graphs
# ---------------------------------------------------------------------------

def _seed_graphs(engine: Engine, user_id: str) -> None:
    if not _GRAPHS_DIR.exists():
        logger.warning("Graph seeding skipped — directory not found: %s", _GRAPHS_DIR)
        return

    yaml_paths = sorted(_GRAPHS_DIR.glob("*.yaml"))
    if not yaml_paths:
        logger.warning("Graph seeding skipped — no YAML files in %s", _GRAPHS_DIR)
        return

    try:
        import yaml as _yaml
    except ImportError:
        logger.warning("Graph seeding skipped — PyYAML not installed")
        return

    now = datetime.utcnow()
    count = 0
    with engine.begin() as conn:
        for yaml_path in yaml_paths:
            try:
                content = yaml_path.read_text(encoding="utf-8")
                parsed = _yaml.safe_load(content) or {}
                graph_name = parsed.get("graph_name") or yaml_path.stem
                description = parsed.get("description") or ""

                conn.execute(
                    text("""
                        INSERT INTO graph_registry
                            (id, user_id, name, description, yaml_content,
                             is_builtin, created_at, updated_at)
                        VALUES
                            (:id, :user_id, :name, :description, :yaml_content,
                             :is_builtin, :created_at, :updated_at)
                        ON CONFLICT (user_id, name) DO UPDATE SET
                            description  = EXCLUDED.description,
                            yaml_content = EXCLUDED.yaml_content,
                            updated_at   = EXCLUDED.updated_at
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "name": graph_name,
                        "description": description,
                        "yaml_content": content,
                        "is_builtin": True,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                count += 1
            except Exception as exc:
                logger.error("Failed to seed graph '%s': %s", yaml_path.name, exc)

    logger.info("✅ Seeded %d graphs into graph_registry for user %s", count, user_id)


# ---------------------------------------------------------------------------
# Delegation sub-agents
# ---------------------------------------------------------------------------

def _seed_agents(engine: Engine, user_id: str) -> None:
    """Seed delegation sub-agents into the agents table for a user.

    Uses WHERE NOT EXISTS so it is safe to re-run without creating duplicates.
    No unique constraint on (user_id, display_name) exists, so ON CONFLICT
    cannot be used here.
    """
    now = datetime.utcnow()
    seeded = 0
    with engine.begin() as conn:
        for agent in _SUB_AGENT_DEFS:
            result = conn.execute(
                text("""
                    INSERT INTO agents
                        (id, user_id, display_name, description,
                         skill_ids, graph_id, status, created_at, updated_at)
                    SELECT
                        :id, :user_id, :display_name, :description,
                        CAST(:skill_ids AS JSON), :graph_id, 'active', :created_at, :updated_at
                    WHERE NOT EXISTS (
                        SELECT 1 FROM agents
                        WHERE user_id = :user_id AND display_name = :display_name
                    )
                """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "display_name": agent["display_name"],
                    "description": agent["description"],
                    "skill_ids": json.dumps(agent["skill_ids"]),
                    "graph_id": agent["graph_id"],
                    "created_at": now,
                    "updated_at": now,
                },
            )
            if result.rowcount:
                seeded += 1

    logger.info(
        "✅ Seeded %d delegation sub-agents into agents for user %s", seeded, user_id
    )

"""
Per-user skill / graph seeder.
Called once at user creation time (auth.py) — NOT at server startup.
Idempotent: ON CONFLICT (user_id, name) DO UPDATE.
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


def seed_user_definitions(engine: Engine, user_id: str) -> None:
    """Seed skill_registry and graph_registry for a specific user.

    Creates one row per skill/graph per user.  Safe to re-run (upsert).
    """
    _seed_skills(engine, user_id)
    _seed_graphs(engine, user_id)


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

"""Skill Pack import service.

Handles importing skill definitions from YAML or Markdown frontmatter files.

Supported formats:
  1. Pure YAML — single skill (top-level keys) or multi-skill (skills: [...])
  2. Markdown with YAML frontmatter — metadata between --- fences, body becomes instructions

Directory layout on disk:
  data/users/{user_id}/skill_packs/{pack_name}.{yaml|yml|md}

API:
  parse_skill_pack(content, filename)  -> list[SkillDef]
  import_skill_pack(user_id, pack_name, content, filename, db, replace=False) -> SkillPackImportResult
  delete_skill_pack(user_id, pack_name, db)
  list_skill_packs(user_id, db) -> list[dict]
  get_skill_pack_content(user_id, pack_name) -> str | None
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Valid pack name: starts with lowercase letter, then lowercase/digit/underscore, 1-50 chars.
_PACK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SkillPackImportResult:
    ok: bool
    skill_names: list[str] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def success(cls, skill_names: list[str]) -> "SkillPackImportResult":
        return cls(ok=True, skill_names=skill_names)

    @classmethod
    def fail(cls, reason: str) -> "SkillPackImportResult":
        return cls(ok=False, error=reason)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_skill_pack(content: str, filename: str) -> list:
    """Parse YAML or Markdown-frontmatter content into a list of SkillDef.

    Supports:
    - Pure YAML: single skill (top-level name/description/tools/instructions)
      or multi-skill (top-level 'skills' key with list of entries)
    - Markdown with YAML frontmatter: YAML block between first --- fences,
      remaining markdown body becomes the `instructions` field (overrides YAML instructions).

    Raises:
        ValueError: if content cannot be parsed or is missing required fields.
    """
    import yaml
    from domains.orchestration2.engine.models.skill import SkillDef

    stripped = content.strip()
    instructions_from_body: str | None = None

    if stripped.startswith("---"):
        # Markdown frontmatter mode
        # Find closing ---
        rest = stripped[3:]  # skip opening ---
        close_idx = rest.find("\n---")
        if close_idx == -1:
            raise ValueError("Unclosed YAML frontmatter — missing closing '---'")
        yaml_block = rest[:close_idx].strip()
        body = rest[close_idx + 4:].strip()  # skip "\n---"
        if body:
            instructions_from_body = body
        data = yaml.safe_load(yaml_block) or {}
    else:
        data = yaml.safe_load(stripped) or {}

    if not isinstance(data, dict):
        raise ValueError("YAML content must be a mapping (dict)")

    skill_entries: list[dict] = []

    if "skills" in data and isinstance(data["skills"], list):
        # Multi-skill format
        skill_entries = data["skills"]
    elif "name" in data:
        # Single-skill format
        skill_entries = [data]
    else:
        raise ValueError("No skill definitions found. Provide either a 'name' key (single skill) or a 'skills' list.")

    result: list[SkillDef] = []
    for entry in skill_entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Each skill entry must be a dict, got: {type(entry).__name__}")
        name = entry.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"Skill entry is missing required 'name' field: {entry}")

        tools = entry.get("tools") or []
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]

        instructions = instructions_from_body or entry.get("instructions") or None

        result.append(SkillDef(
            name=name.strip(),
            description=(entry.get("description") or "").strip() or None,
            tools=list(tools),
            instructions=instructions,
        ))

    if not result:
        raise ValueError("No valid skill definitions found in the pack")

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def import_skill_pack(
    user_id: str,
    pack_name: str,
    content: str,
    filename: str,
    db: AsyncSession,
    *,
    replace: bool = False,
) -> SkillPackImportResult:
    """Validate, parse, save, and register a skill pack.

    Args:
        user_id:   Authenticated user's UUID.
        pack_name: Logical pack name (e.g. "research_skills").
        content:   Raw file content (YAML or Markdown).
        filename:  Original filename including extension (.yaml/.yml/.md).
        db:        Async DB session.
        replace:   If True, overwrite existing pack. If False, fail if exists.
    """
    if not _PACK_NAME_RE.match(pack_name):
        return SkillPackImportResult.fail(
            "pack_name must start with a lowercase letter and contain only "
            "lowercase letters, digits, and underscores (max 50 chars)"
        )

    # Parse before any I/O to catch errors early
    try:
        skill_defs = parse_skill_pack(content, filename)
    except Exception as exc:
        return SkillPackImportResult.fail(f"Parse error: {exc}")

    # Check existence
    exists = await _pack_exists(user_id, pack_name, db)
    if exists and not replace:
        return SkillPackImportResult.fail(
            f"Skill pack '{pack_name}' already exists. "
            "Use PUT /api/definitions/skill-packs/{name} to update it."
        )
    if exists and replace:
        await _delete_pack_db_rows(user_id, pack_name, db)

    # Determine file extension
    ext = Path(filename).suffix.lower() or ".yaml"
    if ext not in {".yaml", ".yml", ".md"}:
        ext = ".yaml"

    # Save content to filesystem
    try:
        from shared.paths import get_user_skill_packs_dir
        packs_dir = get_user_skill_packs_dir(user_id)
        pack_file = packs_dir / f"{pack_name}{ext}"
        pack_file.write_text(content, encoding="utf-8")
    except Exception as exc:
        return SkillPackImportResult.fail(f"Failed to save pack file: {exc}")

    # Upsert skills into DB
    try:
        registered = await _upsert_pack_skills(db, user_id, pack_name, skill_defs, str(pack_file))
    except Exception as exc:
        await db.rollback()
        return SkillPackImportResult.fail(f"DB upsert failed: {exc}")

    await db.commit()
    logger.info("Imported skill pack '%s' for user %s: %d skills", pack_name, user_id, len(registered))
    return SkillPackImportResult.success(registered)


async def delete_skill_pack(user_id: str, pack_name: str, db: AsyncSession) -> None:
    """Remove a skill pack and all its skills from DB and filesystem.

    Raises ValueError if the pack does not exist.
    """
    exists = await _pack_exists(user_id, pack_name, db)
    if not exists:
        raise ValueError(f"No skill pack '{pack_name}' found for this user")

    await _delete_pack_db_rows(user_id, pack_name, db)
    await db.commit()

    # Remove file(s) from filesystem
    try:
        from shared.paths import get_user_skill_packs_dir
        packs_dir = get_user_skill_packs_dir(user_id)
        for ext in (".yaml", ".yml", ".md"):
            f = packs_dir / f"{pack_name}{ext}"
            if f.exists():
                f.unlink()
    except Exception as exc:
        logger.warning("Could not remove pack file for '%s': %s", pack_name, exc)

    logger.info("Deleted skill pack '%s' for user %s", pack_name, user_id)


async def list_skill_packs(user_id: str, db: AsyncSession) -> list[dict]:
    """Return summary of all skill packs for a user.

    Each entry: { pack_name, skills: [{name, description, tools, is_active}], updated_at }
    """
    rows = await db.execute(
        text("""
            SELECT name, description, tools, instructions, is_active, origin_id, updated_at
            FROM skill_registry
            WHERE user_id = :user_id AND origin_type = 'skill_pack'
            ORDER BY origin_id, name
        """),
        {"user_id": user_id},
    )

    packs: dict[str, dict] = {}
    for row in rows.fetchall():
        pack_name = row.origin_id or "unknown"
        if pack_name not in packs:
            packs[pack_name] = {
                "pack_name": pack_name,
                "skills": [],
                "updated_at": None,
            }
        tools_val = row.tools
        if isinstance(tools_val, str):
            try:
                tools_val = json.loads(tools_val)
            except Exception:
                tools_val = []
        packs[pack_name]["skills"].append({
            "name": row.name,
            "description": row.description,
            "tools": tools_val or [],
            "is_active": row.is_active,
        })
        if row.updated_at and (
            packs[pack_name]["updated_at"] is None
            or row.updated_at > packs[pack_name]["updated_at"]
        ):
            packs[pack_name]["updated_at"] = row.updated_at

    return list(packs.values())


async def get_skill_pack_content(user_id: str, pack_name: str) -> str | None:
    """Read the raw file content for a skill pack, or None if not found."""
    try:
        from shared.paths import get_user_skill_packs_dir
        packs_dir = get_user_skill_packs_dir(user_id)
        for ext in (".yaml", ".yml", ".md"):
            f = packs_dir / f"{pack_name}{ext}"
            if f.exists():
                return f.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not read pack content for '%s': %s", pack_name, exc)
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _pack_exists(user_id: str, pack_name: str, db: AsyncSession) -> bool:
    result = await db.execute(
        text("""
            SELECT 1 FROM skill_registry
            WHERE user_id = :user_id AND origin_type = 'skill_pack' AND origin_id = :pack_name
            LIMIT 1
        """),
        {"user_id": user_id, "pack_name": pack_name},
    )
    return result.fetchone() is not None


async def _delete_pack_db_rows(user_id: str, pack_name: str, db: AsyncSession) -> None:
    await db.execute(
        text("""
            DELETE FROM skill_registry
            WHERE user_id = :user_id AND origin_type = 'skill_pack' AND origin_id = :pack_name
        """),
        {"user_id": user_id, "pack_name": pack_name},
    )


async def _upsert_pack_skills(
    db: AsyncSession,
    user_id: str,
    pack_name: str,
    skill_defs: list,
    artifact_path: str,
) -> list[str]:
    now = datetime.utcnow()
    names: list[str] = []
    for skill_def in skill_defs:
        vh = hashlib.sha256(
            json.dumps(
                {"name": skill_def.name, "tools": skill_def.tools}, sort_keys=True
            ).encode()
        ).hexdigest()[:16]
        await db.execute(
            text("""
                INSERT INTO skill_registry
                    (id, user_id, name, description, tools, instructions, is_builtin,
                     origin_type, origin_id, status, is_active,
                     version_hash, artifact_path, activated_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :name, :description,
                     CAST(:tools AS JSON), :instructions, FALSE,
                     'skill_pack', :pack_name, 'active', TRUE,
                     :vh, :artifact_path, :now, :now, :now)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    description  = EXCLUDED.description,
                    tools        = EXCLUDED.tools,
                    instructions = EXCLUDED.instructions,
                    origin_type  = 'skill_pack',
                    origin_id    = EXCLUDED.origin_id,
                    status       = 'active',
                    is_active    = TRUE,
                    version_hash = EXCLUDED.version_hash,
                    artifact_path = EXCLUDED.artifact_path,
                    updated_at   = EXCLUDED.updated_at
            """),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": skill_def.name,
                "description": skill_def.description or "",
                "tools": json.dumps(skill_def.tools),
                "instructions": skill_def.instructions,
                "pack_name": pack_name,
                "vh": vh,
                "artifact_path": artifact_path,
                "now": now,
            },
        )
        names.append(skill_def.name)
    return names

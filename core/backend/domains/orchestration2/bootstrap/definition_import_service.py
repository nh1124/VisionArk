"""Definition import service.

Handles the upload/register flow for user-defined ("upload") modules.
A module is a directory with one or more Python files.  The entry point is
always __init__.py, which must expose at least one of:
  - get_tools(user_id, db) -> list[BaseTool]
  - get_skill_defs() -> list[SkillDef]

Directory layout on disk:
  data/users/{user_id}/custom_tools/{module_name}/
      __init__.py       ← required entry point
      tools.py          ← optional
      skills.py         ← optional
      utils.py          ← optional
      ...

The module is loaded via importlib.util with submodule_search_locations set,
so relative imports (from .tools import MyTool) work correctly.

API:
  import_user_module(user_id, module_name, files, db, replace=False)
  delete_user_module(user_id, module_name, db)
  get_module_files(user_id, module_name) -> dict[str, str]
  list_modules(user_id, db) -> list[dict]
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .definition_validation_service import validate_module_files

logger = logging.getLogger(__name__)

# Valid module name: starts with lowercase letter, then lowercase/digit/underscore; 1-50 chars.
_MODULE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    ok: bool
    tool_names: list[str] = field(default_factory=list)
    skill_names: list[str] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def success(cls, tool_names: list[str], skill_names: list[str]) -> "ImportResult":
        return cls(ok=True, tool_names=tool_names, skill_names=skill_names)

    @classmethod
    def fail(cls, reason: str) -> "ImportResult":
        return cls(ok=False, error=reason)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def import_user_module(
    user_id: str,
    module_name: str,
    files: dict[str, str],
    db: AsyncSession,
    *,
    replace: bool = False,
) -> ImportResult:
    """Validate, save, and register a user-uploaded module.

    Args:
        user_id:     Authenticated user's UUID.
        module_name: Logical directory name (e.g. "my_scraper").
        files:       Mapping of filename → Python source (must include __init__.py).
        db:          Async DB session.
        replace:     If True, delete existing DB rows and files before re-importing.
                     If False, fail if a module with this name already exists.

    Returns:
        ImportResult with tool_names and skill_names on success.
    """
    # 1. Validate module_name format
    if not _MODULE_NAME_RE.match(module_name):
        return ImportResult.fail(
            "module_name must start with a lowercase letter and contain only "
            "lowercase letters, digits, and underscores (max 50 chars)"
        )

    # 2. Validate all files (syntax + security + contract) before any I/O
    validation = validate_module_files(files, module_name=module_name)
    if not validation.ok:
        return ImportResult.fail(validation.error or "Validation failed")

    # 3. Check existence / handle replace
    exists = await _module_exists(user_id, module_name, db)
    if exists and not replace:
        return ImportResult.fail(
            f"Module '{module_name}' already exists. "
            "Use PUT /api/definitions/modules/{name} to update it."
        )
    if exists and replace:
        # Delete old DB rows (file cleanup happens when we overwrite below)
        await _delete_db_rows(user_id, module_name, db)
        _invalidate_module_cache(user_id, module_name)

    # 4. Write files to filesystem
    try:
        from shared.paths import get_user_custom_tools_dir
        module_dir = get_user_custom_tools_dir(user_id, module_name)

        # Remove stale .py files from previous uploads
        for old_py in module_dir.glob("*.py"):
            old_py.unlink(missing_ok=True)

        for filename, content in files.items():
            target = module_dir / filename
            # Safety: no subdirectory writes allowed
            if target.parent != module_dir:
                return ImportResult.fail(
                    f"Subdirectory paths not allowed in filenames: '{filename}'"
                )
            target.write_text(content, encoding="utf-8")

        init_file = module_dir / "__init__.py"
        logger.info("Saved module '%s' (%d files) for user %s", module_name, len(files), user_id)
    except Exception as exc:
        return ImportResult.fail(f"Failed to save module to filesystem: {exc}")

    # 5. Load the module (package-style so relative imports work)
    module_key = _module_key(user_id, module_name)
    try:
        spec = importlib.util.spec_from_file_location(
            module_key,
            init_file,
            submodule_search_locations=[str(module_dir)],
        )
        if spec is None or spec.loader is None:
            raise ImportError("Could not build module spec")
        module = importlib.util.module_from_spec(spec)
        module.__package__ = module_key
        sys.modules[module_key] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        sys.modules.pop(module_key, None)
        _cleanup_module_dir(module_dir)
        return ImportResult.fail(f"Module load error: {exc}")

    # 6. Collect and register tools + skills
    code_hash = _hash_files(files)
    registered_tools: list[str] = []
    registered_skills: list[str] = []

    try:
        import asyncio
        from va_sdk import BaseTool

        # --- Tools ---
        get_tools_fn = getattr(module, "get_tools", None)
        if get_tools_fn is not None:
            if asyncio.iscoroutinefunction(get_tools_fn):
                tool_instances = await get_tools_fn(user_id, db)
            else:
                tool_instances = get_tools_fn(user_id, db)

            if not tool_instances:
                raise ValueError(
                    "get_tools() returned an empty list — at least one tool is required"
                )
            bad = [type(t).__name__ for t in tool_instances if not isinstance(t, BaseTool)]
            if bad:
                raise ValueError(
                    f"get_tools() returned non-BaseTool objects: {', '.join(bad)}"
                )
            registered_tools = await _upsert_tools(
                db, user_id, module_name, tool_instances, code_hash, init_file
            )

        # --- Skills ---
        get_skill_defs_fn = getattr(module, "get_skill_defs", None)
        if get_skill_defs_fn is not None:
            from domains.orchestration2.engine.models.skill import SkillDef
            skill_defs = get_skill_defs_fn()
            if skill_defs:
                bad_skills = [
                    type(s).__name__ for s in skill_defs if not isinstance(s, SkillDef)
                ]
                if bad_skills:
                    raise ValueError(
                        f"get_skill_defs() returned non-SkillDef objects: {', '.join(bad_skills)}"
                    )
                registered_skills = await _upsert_skills(db, user_id, module_name, skill_defs)

    except Exception as exc:
        await db.rollback()
        sys.modules.pop(module_key, None)
        _cleanup_module_dir(module_dir)
        return ImportResult.fail(str(exc))

    await db.commit()
    logger.info(
        "Imported module '%s' for user %s: %d tools, %d skills",
        module_name, user_id, len(registered_tools), len(registered_skills),
    )
    return ImportResult.success(registered_tools, registered_skills)


async def delete_user_module(
    user_id: str,
    module_name: str,
    db: AsyncSession,
) -> None:
    """Remove all DB rows and filesystem artefacts for an upload module.

    Raises ValueError if the module does not exist.
    """
    exists = await _module_exists(user_id, module_name, db)
    if not exists:
        raise ValueError(f"No uploaded module '{module_name}' found for this user")

    await _delete_db_rows(user_id, module_name, db)
    await db.commit()

    _invalidate_module_cache(user_id, module_name)

    try:
        from shared.paths import get_user_custom_tools_dir
        module_dir = get_user_custom_tools_dir(user_id, module_name)
        _cleanup_module_dir(module_dir)
    except Exception as exc:
        logger.warning("Could not remove filesystem artefact for module '%s': %s", module_name, exc)

    logger.info("Deleted upload module '%s' for user %s", module_name, user_id)


def get_module_files(user_id: str, module_name: str) -> dict[str, str]:
    """Read all .py files from a module's directory. Returns filename → content."""
    try:
        from shared.paths import get_user_custom_tools_dir
        module_dir = get_user_custom_tools_dir(user_id, module_name)
        if not module_dir.exists():
            return {}
        result: dict[str, str] = {}
        for py_file in sorted(module_dir.glob("*.py")):
            result[py_file.name] = py_file.read_text(encoding="utf-8")
        return result
    except Exception as exc:
        logger.warning("Could not read files for module '%s': %s", module_name, exc)
        return {}


async def list_modules(user_id: str, db: AsyncSession) -> list[dict]:
    """Return a summary of all uploaded modules for a user.

    Each entry contains the module_name, tools, skills, and timestamps.
    """
    # Fetch all upload tools for this user
    tool_rows = await db.execute(
        text("""
            SELECT name, description, origin_id, is_active, updated_at
            FROM tool_registry
            WHERE user_id = :user_id AND origin_type = 'upload'
            ORDER BY origin_id, name
        """),
        {"user_id": user_id},
    )
    skill_rows = await db.execute(
        text("""
            SELECT name, description, tools, origin_id, is_active, updated_at
            FROM skill_registry
            WHERE user_id = :user_id AND origin_type = 'upload'
            ORDER BY origin_id, name
        """),
        {"user_id": user_id},
    )

    modules: dict[str, dict] = {}

    for row in tool_rows.fetchall():
        origin_id = row.origin_id or row.name
        if origin_id not in modules:
            modules[origin_id] = {
                "module_name": origin_id,
                "tools": [],
                "skills": [],
                "updated_at": None,
            }
        modules[origin_id]["tools"].append({
            "name": row.name,
            "description": row.description,
            "is_active": row.is_active,
        })
        if row.updated_at and (
            modules[origin_id]["updated_at"] is None
            or row.updated_at > modules[origin_id]["updated_at"]
        ):
            modules[origin_id]["updated_at"] = row.updated_at

    for row in skill_rows.fetchall():
        origin_id = row.origin_id or row.name
        if origin_id not in modules:
            modules[origin_id] = {
                "module_name": origin_id,
                "tools": [],
                "skills": [],
                "updated_at": None,
            }
        tools_val = row.tools
        if isinstance(tools_val, str):
            try:
                tools_val = json.loads(tools_val)
            except Exception:
                tools_val = []
        modules[origin_id]["skills"].append({
            "name": row.name,
            "description": row.description,
            "tools": tools_val or [],
            "is_active": row.is_active,
        })

    return list(modules.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _module_key(user_id: str, module_name: str) -> str:
    return f"__user_custom_{user_id}_{module_name}__"


def _invalidate_module_cache(user_id: str, module_name: str) -> None:
    key = _module_key(user_id, module_name)
    # Remove the package and any submodules
    to_remove = [k for k in sys.modules if k == key or k.startswith(f"{key}.")]
    for k in to_remove:
        sys.modules.pop(k, None)


async def _module_exists(user_id: str, module_name: str, db: AsyncSession) -> bool:
    result = await db.execute(
        text("""
            SELECT 1 FROM tool_registry
            WHERE user_id = :user_id AND origin_type = 'upload' AND origin_id = :oid
            UNION ALL
            SELECT 1 FROM skill_registry
            WHERE user_id = :user_id AND origin_type = 'upload' AND origin_id = :oid
            LIMIT 1
        """),
        {"user_id": user_id, "oid": module_name},
    )
    return result.fetchone() is not None


async def _delete_db_rows(user_id: str, module_name: str, db: AsyncSession) -> None:
    await db.execute(
        text("""
            DELETE FROM tool_registry
            WHERE user_id = :user_id AND origin_type = 'upload' AND origin_id = :oid
        """),
        {"user_id": user_id, "oid": module_name},
    )
    await db.execute(
        text("""
            DELETE FROM skill_registry
            WHERE user_id = :user_id AND origin_type = 'upload' AND origin_id = :oid
        """),
        {"user_id": user_id, "oid": module_name},
    )


def _hash_files(files: dict[str, str]) -> str:
    combined = json.dumps(sorted(files.items()), sort_keys=True)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _cleanup_module_dir(module_dir) -> None:
    try:
        for f in module_dir.glob("*.py"):
            f.unlink(missing_ok=True)
        if module_dir.exists() and not any(module_dir.iterdir()):
            module_dir.rmdir()
    except Exception as exc:
        logger.warning("Cleanup of module dir '%s' failed: %s", module_dir, exc)


async def _upsert_tools(
    db: AsyncSession,
    user_id: str,
    module_name: str,
    tool_instances: list,
    code_hash: str,
    init_file,
) -> list[str]:
    now = datetime.utcnow()
    names: list[str] = []
    for tool_instance in tool_instances:
        vh = hashlib.sha256(
            json.dumps(
                {"name": tool_instance.name, "description": tool_instance.description},
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
        await db.execute(
            text("""
                INSERT INTO tool_registry
                    (id, user_id, name, description, params_schema,
                     origin_type, origin_id, status, is_active,
                     version_hash, artifact_path, artifact_hash,
                     activated_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :name, :description,
                     CAST(:params_schema AS JSON),
                     'upload', :origin_id, 'active', TRUE,
                     :vh, :artifact_path, :artifact_hash,
                     :now, :now, :now)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    description   = EXCLUDED.description,
                    params_schema = EXCLUDED.params_schema,
                    origin_type   = 'upload',
                    origin_id     = EXCLUDED.origin_id,
                    status        = 'active',
                    is_active     = TRUE,
                    version_hash  = EXCLUDED.version_hash,
                    artifact_path = EXCLUDED.artifact_path,
                    artifact_hash = EXCLUDED.artifact_hash,
                    updated_at    = EXCLUDED.updated_at
            """),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": tool_instance.name,
                "description": tool_instance.description or "",
                "params_schema": json.dumps({}),
                "origin_id": module_name,
                "vh": vh,
                "artifact_path": str(init_file),
                "artifact_hash": code_hash,
                "now": now,
            },
        )
        names.append(tool_instance.name)
    return names


async def _upsert_skills(
    db: AsyncSession,
    user_id: str,
    module_name: str,
    skill_defs: list,
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
                    (id, user_id, name, description, tools, is_builtin,
                     origin_type, origin_id, status, is_active,
                     version_hash, activated_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :name, :description,
                     CAST(:tools AS JSON), FALSE,
                     'upload', :origin_id, 'active', TRUE,
                     :vh, :now, :now, :now)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    description  = EXCLUDED.description,
                    tools        = EXCLUDED.tools,
                    origin_type  = 'upload',
                    origin_id    = EXCLUDED.origin_id,
                    status       = 'active',
                    is_active    = TRUE,
                    version_hash = EXCLUDED.version_hash,
                    updated_at   = EXCLUDED.updated_at
            """),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": skill_def.name,
                "description": skill_def.description or "",
                "tools": json.dumps(skill_def.tools),
                "origin_id": module_name,
                "vh": vh,
                "now": now,
            },
        )
        names.append(skill_def.name)
    return names

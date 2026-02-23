"""File management tools: write, read chunk, list, delete, patch, move, copy, mkdir, stat."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import (
    fail,
    get_db,
    get_file_service,
    get_project_id,
    get_user_api_key,
    get_user_id,
    make_result,
)
from shared.paths import get_project_dir, secure_path_join


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

def _hash(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def _ok(call: ToolCallRef, msg: str, **extra) -> ToolResult:
    payload: dict = {"success": True, "message": msg, "error_code": None}
    payload.update({k: v for k, v in extra.items() if v is not None})
    return make_result(call, json.dumps(payload))


def _err(call: ToolCallRef, code: str, msg: str) -> ToolResult:
    payload = {"success": False, "error_code": code, "message": msg}
    return fail(call, json.dumps(payload))


async def _sync(ctx: ExecutionContext) -> None:
    """Sync project directory to DB, logging any errors."""
    try:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        from domains.workspace.file_service import FileService
        file_svc = FileService(db, user_id)
        await file_svc.sync_project_directory(project_id)
    except Exception as e:
        print(f"[sync] {e}")


def _resolve_root(ctx: ExecutionContext) -> Path:
    return get_project_dir(get_user_id(ctx), get_project_id(ctx))


def _find_file(root: Path, file_path: str) -> Path | None:
    """Search project root and well-known subdirs for a relative path."""
    p = secure_path_join(root, file_path)
    if p.exists():
        return p
    for sub in ("refs", "files", "artifacts"):
        try:
            candidate = secure_path_join(root / sub, file_path)
            if candidate.exists():
                return candidate
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# WriteFileTool
# ---------------------------------------------------------------------------

class WriteFileTool:
    definition = ToolDef(
        name="write_file",
        description=(
            "Write content to a file in the project's artifacts directory. "
            "file_path is always relative to artifacts/ — never include the 'artifacts/' prefix. "
            "Examples: 'report.md' → artifacts/report.md, 'plans/v1.md' → artifacts/plans/v1.md. "
            "Overwriting is disabled by default."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path relative to artifacts/ (e.g. 'report.md' or 'plans/v1.md'). Never include 'artifacts/' prefix.",
                },
                "content": {"type": "string", "description": "Content to write"},
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite if file exists (default false)",
                },
            },
            "required": ["file_path", "content"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")
        content = call.arguments.get("content", "")
        overwrite = call.arguments.get("overwrite", False)

        # Strip any leading artifacts/ the agent may have included, then re-add it
        normalized = file_path.removeprefix("artifacts/")
        file_path = f"artifacts/{normalized}"

        try:
            root = _resolve_root(ctx)
            p = secure_path_join(root, file_path)
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid path: {file_path}")

        if p.exists() and not overwrite:
            return _err(call, "ALREADY_EXISTS", f"File already exists: {file_path}. Set overwrite=true to replace.")

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception as e:
            return _err(call, "IO_ERROR", f"Write failed: {e}")

        await _sync(ctx)
        rel = p.relative_to(root).as_posix()
        return _ok(call, f"Written to {rel}", path=rel, bytes=len(content.encode("utf-8")), hash=_hash(p))


# ---------------------------------------------------------------------------
# ReadFileChunkTool
# ---------------------------------------------------------------------------

class ReadFileChunkTool:
    definition = ToolDef(
        name="read_file_chunk",
        description=(
            "Read a file (or a line range) from the project. "
            "Searches project root, refs/, files/, and artifacts/ automatically. "
            "Use start_line/end_line to read a subset of lines (1-indexed)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path to the file"},
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-indexed, default 1)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to return (inclusive). Omit for end of file.",
                },
            },
            "required": ["file_path"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        if ctx.engine_kind == "gemini":
            return await self._invoke_gemini(call, ctx)
        return await self._invoke_generic(call, ctx)

    async def _invoke_gemini(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        """Gemini-native: upload file via Files API and return minimal JSON envelope."""
        file_path = call.arguments.get("file_path", "")
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            root = _resolve_root(ctx)
            p = _find_file(root, file_path)
            if not p:
                return _err(call, "NOT_FOUND", f"File not found: {file_path}")

            raw = p.read_bytes()
            is_binary = b"\x00" in raw

            def sanitize(data: bytes) -> str:
                return data.decode("utf-8", errors="replace").replace("\x00", "")

            from google.genai import types as genai_types

            provider_parts: list[Any] = []
            gemini_uri: str | None = None
            gemini_mime: str | None = None

            try:
                api_key = await get_user_api_key(ctx)
                if api_key:
                    from domains.workspace.file_service import FileService
                    service = FileService(db, user_id, api_key)
                    gemini_info = await service.ensure_gemini_upload(
                        local_path=p, filename=p.name, project_id=project_id,
                    )
                    if gemini_info and gemini_info.get("gemini_file_uri"):
                        gemini_uri = gemini_info["gemini_file_uri"]
                        gemini_mime = gemini_info.get("mime_type", "application/octet-stream")
                        provider_parts.append(
                            genai_types.Part.from_uri(
                                file_uri=gemini_uri, mime_type=gemini_mime,
                            )
                        )
            except Exception:
                pass

            rel = p.relative_to(root).as_posix()
            if gemini_uri:
                output = json.dumps({
                    "success": True,
                    "path": rel,
                    "message": f"File available via Gemini: {p.name} ({gemini_mime}, uri={gemini_uri})",
                    "error_code": None,
                })
            else:
                text = sanitize(raw)
                start_line = max(1, call.arguments.get("start_line", 1))
                end_line = call.arguments.get("end_line", None)
                lines = text.splitlines(keepends=True)
                total = len(lines)
                chunk = lines[start_line - 1: end_line] if end_line else lines[start_line - 1:]
                content = "".join(chunk)
                output = json.dumps({
                    "success": True,
                    "path": rel,
                    "content": content,
                    "start_line": start_line,
                    "end_line": start_line + len(chunk) - 1,
                    "total_lines": total,
                    "truncated": False,
                    "error_code": None,
                })

            return make_result(call, output, provider_parts=provider_parts)
        except Exception as e:
            return _err(call, "IO_ERROR", f"Failed to read file (gemini): {e}")

    async def _invoke_generic(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")
        start_line = max(1, call.arguments.get("start_line", 1))
        end_line = call.arguments.get("end_line", None)

        try:
            root = _resolve_root(ctx)
            p = _find_file(root, file_path)
            if not p:
                return _err(call, "NOT_FOUND", f"File not found: {file_path}")

            raw = p.read_bytes()
            text = raw.decode("utf-8", errors="replace").replace("\x00", "")
            lines = text.splitlines(keepends=True)
            total = len(lines)
            chunk = lines[start_line - 1: end_line] if end_line else lines[start_line - 1:]
            content = "".join(chunk)
            truncated = False
            if len(content) > 100_000:
                content = content[:100_000]
                truncated = True

            rel = p.relative_to(root).as_posix()
            payload = {
                "success": True,
                "path": rel,
                "content": content,
                "start_line": start_line,
                "end_line": start_line + len(chunk) - 1,
                "total_lines": total,
                "truncated": truncated,
                "error_code": None,
            }
            return make_result(call, json.dumps(payload))
        except Exception as e:
            return _err(call, "IO_ERROR", f"Failed to read file: {e}")


# ---------------------------------------------------------------------------
# ListFilesTool
# ---------------------------------------------------------------------------

class ListFilesTool:
    definition = ToolDef(
        name="list_files",
        description="List files and directories within the project (or a subdirectory).",
        parameters={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Project-root-relative subdirectory to list. Default: project root.",
                },
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        directory = call.arguments.get("directory") or call.arguments.get("path", "")

        try:
            root = _resolve_root(ctx)
            target = secure_path_join(root, directory) if directory else root
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid directory: {directory}")

        if not target.exists():
            return _err(call, "NOT_FOUND", f"Directory not found: {directory}")

        try:
            entries = []
            for item in sorted(target.iterdir()):
                rel = item.relative_to(root).as_posix()
                kind = "dir" if item.is_dir() else "file"
                size = item.stat().st_size if item.is_file() else 0
                entries.append({"path": rel, "type": kind, "size_bytes": size})

            payload = {"success": True, "entries": entries, "error_code": None}
            return make_result(call, json.dumps(payload))
        except Exception as e:
            return _err(call, "IO_ERROR", f"Failed to list files: {e}")


# ---------------------------------------------------------------------------
# DeleteFileTool
# ---------------------------------------------------------------------------

class DeleteFileTool:
    definition = ToolDef(
        name="delete_file",
        description="Permanently delete a file from the project. IRREVERSIBLE.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Project-root-relative path to delete (e.g. 'artifacts/old.md')",
                },
            },
            "required": ["file_path"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")

        try:
            root = _resolve_root(ctx)
            p = secure_path_join(root, file_path)
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid path: {file_path}")

        if not p.exists():
            return _err(call, "NOT_FOUND", f"File not found: {file_path}")

        try:
            p.unlink()
        except Exception as e:
            return _err(call, "IO_ERROR", f"Delete failed: {e}")

        await _sync(ctx)
        rel = file_path
        return _ok(call, f"Deleted: {rel}", path=rel)


# ---------------------------------------------------------------------------
# ApplyTextPatchTool
# ---------------------------------------------------------------------------

class ApplyTextPatchTool:
    definition = ToolDef(
        name="apply_text_patch",
        description=(
            "Apply line-based patches to a text file. "
            "Each patch specifies an operation (replace/insert/delete) and a line range. "
            "Patches are applied bottom-up to avoid line number drift. "
            "Optionally supply expected_hash for optimistic locking."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Project-root-relative path to the file",
                },
                "patches": {
                    "type": "array",
                    "description": (
                        "List of patch operations. Each item: "
                        "{op: 'replace'|'insert'|'delete', start_line: int, end_line: int, content: str}"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["replace", "insert", "delete"]},
                            "start_line": {"type": "integer"},
                            "end_line": {"type": "integer"},
                            "content": {"type": "string"},
                        },
                        "required": ["op", "start_line"],
                    },
                },
                "expected_hash": {
                    "type": "string",
                    "description": "Expected sha256 hash of the file before patching (optimistic lock). Omit to skip.",
                },
            },
            "required": ["file_path", "patches"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")
        patches = call.arguments.get("patches", [])
        expected_hash = call.arguments.get("expected_hash")

        try:
            root = _resolve_root(ctx)
            p = secure_path_join(root, file_path)
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid path: {file_path}")

        if not p.exists():
            return _err(call, "NOT_FOUND", f"File not found: {file_path}")

        try:
            # Optimistic lock
            if expected_hash:
                current_hash = _hash(p)
                if current_hash != expected_hash:
                    return _err(
                        call,
                        "HASH_MISMATCH",
                        f"File has changed. Expected {expected_hash}, got {current_hash}.",
                    )

            text = p.read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)

            # Sort patches by start_line descending (bottom-up application)
            sorted_patches = sorted(patches, key=lambda x: x.get("start_line", 1), reverse=True)

            for patch in sorted_patches:
                op = patch.get("op", "replace")
                start = max(1, patch.get("start_line", 1))
                end = patch.get("end_line", start)
                content = patch.get("content", "")

                # Convert to 0-indexed
                s = start - 1
                e = end  # exclusive slice end

                if op == "replace":
                    new_lines = content.splitlines(keepends=True)
                    # Ensure trailing newline on last replacement line if original had one
                    if new_lines and not new_lines[-1].endswith("\n"):
                        new_lines[-1] += "\n"
                    lines[s:e] = new_lines
                elif op == "insert":
                    # Insert before start_line
                    new_lines = content.splitlines(keepends=True)
                    if new_lines and not new_lines[-1].endswith("\n"):
                        new_lines[-1] += "\n"
                    lines[s:s] = new_lines
                elif op == "delete":
                    lines[s:e] = []

            p.write_text("".join(lines), encoding="utf-8")
        except Exception as e:
            return _err(call, "IO_ERROR", f"Patch failed: {e}")

        await _sync(ctx)
        rel = p.relative_to(root).as_posix()
        new_hash = _hash(p)
        return _ok(call, f"Patch applied to {rel}", path=rel, hash=new_hash)


# ---------------------------------------------------------------------------
# MoveFileTool
# ---------------------------------------------------------------------------

class MoveFileTool:
    definition = ToolDef(
        name="move_file",
        description="Move or rename a file within the project.",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source path (project-root-relative)"},
                "dst": {"type": "string", "description": "Destination path (project-root-relative)"},
                "overwrite": {"type": "boolean", "description": "Overwrite destination if it exists (default false)"},
            },
            "required": ["src", "dst"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        src = call.arguments.get("src", "")
        dst = call.arguments.get("dst", "")
        overwrite = call.arguments.get("overwrite", False)

        try:
            root = _resolve_root(ctx)
            src_p = secure_path_join(root, src)
            dst_p = secure_path_join(root, dst)
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid path in src={src!r} or dst={dst!r}")

        if not src_p.exists():
            return _err(call, "NOT_FOUND", f"Source not found: {src}")
        if dst_p.exists() and not overwrite:
            return _err(call, "ALREADY_EXISTS", f"Destination already exists: {dst}. Set overwrite=true.")

        try:
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(src_p), str(dst_p))
        except Exception as e:
            return _err(call, "IO_ERROR", f"Move failed: {e}")

        await _sync(ctx)
        src_rel = src_p.relative_to(root).as_posix() if src_p.exists() else src
        dst_rel = dst_p.relative_to(root).as_posix()
        payload = {"success": True, "src": src, "dst": dst_rel, "message": f"Moved {src} → {dst_rel}", "error_code": None}
        return make_result(call, json.dumps(payload))


# ---------------------------------------------------------------------------
# CopyFileTool
# ---------------------------------------------------------------------------

class CopyFileTool:
    definition = ToolDef(
        name="copy_file",
        description="Copy a file or directory within the project.",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source path (project-root-relative)"},
                "dst": {"type": "string", "description": "Destination path (project-root-relative)"},
                "overwrite": {"type": "boolean", "description": "Overwrite destination if it exists (default false)"},
            },
            "required": ["src", "dst"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        src = call.arguments.get("src", "")
        dst = call.arguments.get("dst", "")
        overwrite = call.arguments.get("overwrite", False)

        try:
            root = _resolve_root(ctx)
            src_p = secure_path_join(root, src)
            dst_p = secure_path_join(root, dst)
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid path in src={src!r} or dst={dst!r}")

        if not src_p.exists():
            return _err(call, "NOT_FOUND", f"Source not found: {src}")
        if dst_p.exists() and not overwrite:
            return _err(call, "ALREADY_EXISTS", f"Destination already exists: {dst}. Set overwrite=true.")

        try:
            import shutil
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            if src_p.is_dir():
                if dst_p.exists():
                    shutil.rmtree(dst_p)
                shutil.copytree(str(src_p), str(dst_p))
            else:
                shutil.copy2(str(src_p), str(dst_p))
        except Exception as e:
            return _err(call, "IO_ERROR", f"Copy failed: {e}")

        await _sync(ctx)
        dst_rel = dst_p.relative_to(root).as_posix()
        payload = {"success": True, "src": src, "dst": dst_rel, "message": f"Copied {src} → {dst_rel}", "error_code": None}
        return make_result(call, json.dumps(payload))


# ---------------------------------------------------------------------------
# MakeDirectoryTool
# ---------------------------------------------------------------------------

class MakeDirectoryTool:
    definition = ToolDef(
        name="make_directory",
        description="Create a directory (including parents) within the project.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project-root-relative directory path to create"},
                "parents": {
                    "type": "boolean",
                    "description": "Create parent directories as needed (default true)",
                },
            },
            "required": ["path"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        dir_path = call.arguments.get("path", "")
        parents = call.arguments.get("parents", True)

        try:
            root = _resolve_root(ctx)
            p = secure_path_join(root, dir_path)
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid path: {dir_path}")

        try:
            p.mkdir(parents=parents, exist_ok=True)
        except Exception as e:
            return _err(call, "IO_ERROR", f"mkdir failed: {e}")

        await _sync(ctx)
        rel = p.relative_to(root).as_posix()
        return _ok(call, f"Directory created: {rel}", path=rel)


# ---------------------------------------------------------------------------
# GetFileStatTool
# ---------------------------------------------------------------------------

class GetFileStatTool:
    definition = ToolDef(
        name="get_file_stat",
        description="Get metadata (size, hash, mtime) for a file or directory.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Project-root-relative path"},
            },
            "required": ["file_path"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")

        try:
            root = _resolve_root(ctx)
            p = secure_path_join(root, file_path)
        except Exception:
            return _err(call, "INVALID_PATH", f"Invalid path: {file_path}")

        if not p.exists():
            return _err(call, "NOT_FOUND", f"Path not found: {file_path}")

        import datetime as _dt
        st = p.stat()
        rel = p.relative_to(root).as_posix()
        payload = {
            "success": True,
            "path": rel,
            "size_bytes": st.st_size if not p.is_dir() else 0,
            "hash": _hash(p) if p.is_file() else None,
            "mtime": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(),
            "is_dir": p.is_dir(),
            "error_code": None,
            "message": "OK",
        }
        return make_result(call, json.dumps(payload))


# ---------------------------------------------------------------------------
# ImportGitHubRepoTool  (unchanged)
# ---------------------------------------------------------------------------

class ImportGitHubRepoTool:
    definition = ToolDef(
        name="import_github_repo",
        description="Clone a GitHub repository into refs/sources/github directory.",
        parameters={
            "type": "object",
            "properties": {
                "repo_url": {"type": "string", "description": "GitHub repository URL"},
                "branch": {"type": "string", "description": "Branch to clone (default: main)"},
            },
            "required": ["repo_url"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        import asyncio
        import shutil

        repo_url = call.arguments.get("repo_url", "")
        branch = call.arguments.get("branch", "main")
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            root = get_project_dir(user_id, project_id)
            repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
            dest = root / "refs" / "sources" / "github" / repo_name
            dest.mkdir(parents=True, exist_ok=True)

            if any(dest.iterdir()):
                shutil.rmtree(dest)
                dest.mkdir(parents=True, exist_ok=True)

            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", "--branch", branch, repo_url, str(dest),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                return fail(call, f"Git clone failed: {stderr.decode()}")

            return make_result(call, f"Cloned {repo_url} (branch: {branch}) to refs/sources/github/{repo_name}")
        except Exception as e:
            return fail(call, f"Failed to import repo: {e}")

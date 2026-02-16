"""File management tools: save, read, list, delete artifacts."""

from __future__ import annotations

from pathlib import Path

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
    resolve_artifacts_dir,
)
from shared.paths import get_project_dir, secure_path_join


class SaveArtifactTool:
    definition = ToolDef(
        name="save_artifact",
        description=(
            "Save content to a file in the project's artifacts directory. "
            "ATTENTION: Overwriting is disabled by default (overwrite=False). "
            "ORGANIZATION: Use subdirectories (e.g., 'reports/analysis.md')."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path within artifacts (e.g., 'plans/v1.md')"},
                "content": {"type": "string", "description": "Content to write"},
                "overwrite": {"type": "boolean", "description": "Whether to overwrite existing file"},
            },
            "required": ["file_path", "content"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "") or call.arguments.get("filename", "")
        content = call.arguments.get("content", "")
        overwrite = call.arguments.get("overwrite", False)

        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            root_dir = get_project_dir(user_id, project_id)
            if file_path.startswith("artifacts/"):
                p = secure_path_join(root_dir, file_path)
            else:
                artifacts_dir = await resolve_artifacts_dir(ctx)
                p = secure_path_join(artifacts_dir, file_path)

            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists() and not overwrite:
                return fail(call, f"File {file_path} already exists and overwrite is False")

            p.write_text(content, encoding="utf-8")
            actual_rel = p.relative_to(root_dir).as_posix()

            try:
                from domains.workspace.file_service import FileService

                file_svc = FileService(db, user_id)
                await file_svc.sync_project_directory(project_id)
            except Exception:
                pass

            return make_result(call, f"Saved artifact to {actual_rel}")
        except Exception as e:
            return fail(call, f"Failed to save artifact: {e}")


class ReadReferenceTool:
    definition = ToolDef(
        name="read_reference",
        description=(
            "Read a file from the project's storage. Searches root and subdirectories. "
            "HOW TO USE: read_reference(file_path=\"manual.pdf\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path to the file"},
            },
            "required": ["file_path"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        # Support 'path' and 'filename' aliases for 'file_path'
        file_path = (
            call.arguments.get("file_path") 
            or call.arguments.get("path") 
            or call.arguments.get("filename", "")
        )
        
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            d = get_project_dir(user_id, project_id)
            p = secure_path_join(d, file_path)
            if not p.exists():
                for sub in ["refs", "files", "artifacts"]:
                    try:
                        p = secure_path_join(d / sub, file_path)
                        if p.exists():
                            break
                    except Exception:
                        pass

            if not p.exists():
                return fail(call, f"File not found: {file_path}")

            # 1. Read Raw Content (Bytes) first to check for binary
            raw_content = p.read_bytes()
            
            # Simple heuristic: null byte = binary
            is_binary = b"\x00" in raw_content

            # Helper to sanitize text if we need to return text content
            def get_sanitized_text(data: bytes) -> str:
                # Decode with replacement, then remove broken nulls
                text = data.decode("utf-8", errors="replace")
                return text.replace("\x00", "")

            final_text_content = ""
            gemini_upload_success = False
            gemini_uri = None

            # Gemini upload for multimodal (Attempt for ALL files, but critical for binary)
            try:
                from sqlalchemy import select
                from shared.database import UserSettings

                result = await db.execute(
                    select(UserSettings).filter(UserSettings.user_id == user_id)
                )
                user_settings = result.scalars().first()
                api_key = user_settings.gemini_api_key if user_settings else None

                if api_key:
                    from domains.workspace.file_service import FileService

                    service = FileService(db, user_id, api_key)
                    # For binary files, we need to ensure we pass the path correctly
                    gemini_info = await service.ensure_gemini_upload(
                        local_path=p, filename=p.name, project_id=project_id
                    )
                    if gemini_info and gemini_info.get("gemini_file_uri"):
                        gemini_uri = gemini_info['gemini_file_uri']
                        gemini_upload_success = True
            except Exception:
                pass

            # Logic Decision Tree
            if is_binary:
                if gemini_upload_success:
                    # Case A: Binary + Gemini Success -> Placeholder ONLY
                    return make_result(call, f"[Binary File uploaded to Gemini: {gemini_uri}]")
                else:
                    # Case B: Binary + Gemini Fail -> Sanitized Text
                    final_text_content = get_sanitized_text(raw_content)
            else:
                # Case C: Text File -> Text Content (+ URI if available)
                final_text_content = get_sanitized_text(raw_content) # Sanitize anyway to be safe
                if gemini_upload_success:
                    final_text_content += f"\n[Gemini File URI: {gemini_uri}]"

            if len(final_text_content) > 50000:
                final_text_content = final_text_content[:50000] + "\n... (truncated)"

            return make_result(call, final_text_content)
        except Exception as e:
            return fail(call, f"Failed to read file: {e}")


class ListFilesTool:
    definition = ToolDef(
        name="list_files",
        description="List files within project subdirectories.",
        parameters={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Subdirectory to list (refs, artifacts, files). Default: root",
                },
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        # Support 'path' alias for 'directory' to handle common LLM hallucinations
        directory = call.arguments.get("directory") or call.arguments.get("path", "")
        
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            root = get_project_dir(user_id, project_id)
            target = secure_path_join(root, directory) if directory else root

            if not target.exists():
                return make_result(call, f"Directory '{directory}' does not exist.")

            entries = []
            for item in sorted(target.iterdir()):
                rel = item.relative_to(root).as_posix()
                kind = "dir" if item.is_dir() else "file"
                size = item.stat().st_size if item.is_file() else 0
                entries.append(f"[{kind}] {rel} ({size} bytes)" if kind == "file" else f"[{kind}] {rel}/")

            return make_result(call, "\n".join(entries) if entries else "Empty directory.")
        except Exception as e:
            return fail(call, f"Failed to list files: {e}")


class DeleteArtifactTool:
    definition = ToolDef(
        name="delete_artifact",
        description="Permanently delete a file from artifacts. IRREVERSIBLE.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path within artifacts"},
            },
            "required": ["file_path"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            artifacts_dir = await resolve_artifacts_dir(ctx)
            p = secure_path_join(artifacts_dir, file_path)

            if not p.exists():
                return fail(call, f"File not found: {file_path}")

            p.unlink()

            try:
                from domains.workspace.file_service import FileService

                file_svc = FileService(db, user_id)
                await file_svc.sync_project_directory(project_id)
            except Exception:
                pass

            return make_result(call, f"Deleted artifact: {file_path}")
        except Exception as e:
            return fail(call, f"Failed to delete: {e}")


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

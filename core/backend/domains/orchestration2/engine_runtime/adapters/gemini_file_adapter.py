"""GeminiFileAdapter — Gemini-native specialisation for file-reading tools.

When the engine kind is ``"gemini"`` and the tool is ``"read_reference"``,
this adapter:

1. Resolves the file using the same logic as the base ``ReadReferenceTool``.
2. Uploads the file to Gemini via ``FileService.ensure_gemini_upload()``.
3. Builds a native ``Part.from_uri()`` and attaches it to
   ``ToolResult.provider_parts`` so the engine can inject it directly
   into the Gemini Content history.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from google.genai import types as genai_types

from ...engine.models.execution import ExecutionContext, ToolResult
from ...engine.models.message import ToolCallRef
from ...tools.base import get_db, get_project_id, get_user_id
from ...engine.registry.tool_dispatcher import EngineToolAdapter

logger = logging.getLogger(__name__)

_HANDLED_TOOLS = {"read_reference"}


class GeminiFileAdapter:
    """Specialises file-reading tools for the Gemini engine.

    Performs a Gemini file upload and returns a native ``Part.from_uri``
    via ``ToolResult.provider_parts``.  Text content is still returned
    in ``ToolResult.output`` for logging / fallback purposes.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ── EngineToolAdapter protocol ───────────────────────────────────

    def can_handle(self, engine_kind: str, tool_name: str) -> bool:
        return engine_kind == "gemini" and tool_name in _HANDLED_TOOLS

    async def invoke_native(
        self,
        engine_kind: str,
        call: ToolCallRef,
        ctx: ExecutionContext,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ToolResult:
        file_path = (
            call.arguments.get("file_path")
            or call.arguments.get("path")
            or call.arguments.get("filename", "")
        )

        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            from shared.paths import get_project_dir, secure_path_join

            d = get_project_dir(user_id, project_id)
            p = secure_path_join(d, file_path)
            if not p.exists():
                for sub in ("refs", "files", "artifacts"):
                    try:
                        p = secure_path_join(d / sub, file_path)
                        if p.exists():
                            break
                    except Exception:
                        pass

            if not p.exists():
                return ToolResult(
                    tool_name=call.tool_name,
                    call_id=call.call_id,
                    output=f"File not found: {file_path}",
                    error=f"File not found: {file_path}",
                )

            # Read raw content for text fallback
            raw_content = p.read_bytes()
            is_binary = b"\x00" in raw_content

            def sanitize(data: bytes) -> str:
                return data.decode("utf-8", errors="replace").replace("\x00", "")

            # ── Gemini upload ────────────────────────────────────
            provider_parts: list[Any] = []
            gemini_uri: str | None = None
            gemini_mime: str | None = None

            try:
                from domains.workspace.file_service import FileService

                service = FileService(db, user_id, self._api_key)
                gemini_info = await service.ensure_gemini_upload(
                    local_path=p, filename=p.name, project_id=project_id,
                )
                if gemini_info and gemini_info.get("gemini_file_uri"):
                    gemini_uri = gemini_info["gemini_file_uri"]
                    gemini_mime = gemini_info.get(
                        "mime_type", "application/octet-stream"
                    )
                    provider_parts.append(
                        genai_types.Part.from_uri(
                            file_uri=gemini_uri,
                            mime_type=gemini_mime,
                        )
                    )
                    logger.debug(
                        "GeminiFileAdapter: uploaded %s → %s",
                        p.name, gemini_uri,
                    )
            except Exception:
                logger.debug(
                    "GeminiFileAdapter: Gemini upload failed for %s",
                    p.name, exc_info=True,
                )

            # ── Build output text ────────────────────────────────
            # When upload succeeds, return only a minimal placeholder —
            # the native Part.from_uri provides the actual content to
            # Gemini, so including the full text would waste context.
            if gemini_uri:
                output = (
                    f"[File available via Gemini: {p.name} "
                    f"({gemini_mime}, uri={gemini_uri})]"
                )
            elif is_binary:
                output = sanitize(raw_content)
            else:
                output = sanitize(raw_content)
                if len(output) > 50000:
                    output = output[:50000] + "\n... (truncated)"

            return ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                output=output,
                provider_parts=provider_parts,
            )

        except Exception as exc:
            return ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                output=f"Error: {exc}",
                error=str(exc),
            )

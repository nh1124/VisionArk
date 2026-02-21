"""Workspace tools: list, read, create, and update shared workspace items."""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, get_user_id, make_result


class ListWorkspaceItemsTool:
    definition = ToolDef(
        name="list_workspace_items",
        description=(
            "List shared workspace items owned by the current user. "
            "Items hold reusable context like personal profile, company info, and values. "
            "Optionally filter by scope ('private', 'org', 'project') or a search query."
        ),
        parameters={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["private", "org", "project"],
                    "description": "Filter by scope. Omit to return all scopes.",
                },
                "search": {
                    "type": "string",
                    "description": "Optional keyword to filter by title, path, or content.",
                },
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        user_id = get_user_id(ctx)
        db = get_db(ctx)
        scope = call.arguments.get("scope")
        search = call.arguments.get("search")

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            items = await svc.list_items(scope=scope, search=search)

            if not items:
                return make_result(call, "No workspace items found.")

            lines = [f"Found {len(items)} workspace item(s):"]
            for item in items:
                tags_str = f" tags=[{', '.join(item.tags)}]" if item.tags else ""
                lines.append(
                    f"- [{item.id}] {item.title}  path={item.path}  scope={item.scope}{tags_str}"
                )
            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list workspace items: {e}")


class ReadWorkspaceItemTool:
    definition = ToolDef(
        name="read_workspace_item",
        description=(
            "Read the full content of a specific workspace item by its ID. "
            "Use list_workspace_items first to get item IDs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "UUID of the workspace item to read.",
                },
            },
            "required": ["item_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        item_id = call.arguments.get("item_id", "")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            item = await svc.get_item(item_id)

            lines = [
                f"# {item.title}",
                f"path: {item.path}  |  scope: {item.scope}  |  version: {item.version}",
            ]
            if item.tags:
                lines.append(f"tags: {', '.join(item.tags)}")
            lines.append("")
            lines.append(item.content or "(empty)")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to read workspace item: {e}")


class CreateWorkspaceItemTool:
    definition = ToolDef(
        name="create_workspace_item",
        description=(
            "Create a new shared workspace item to store reusable context "
            "(e.g. personal profile, company values, meeting templates). "
            "Use scope='private' for personal info, 'org' for company-wide, 'project' for project-specific."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Human-readable title, e.g. 'About Me'.",
                },
                "path": {
                    "type": "string",
                    "description": "Logical path, e.g. 'profile/about.md' or 'company/values.md'.",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown content to store.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["private", "org", "project"],
                    "description": "Visibility scope. Defaults to 'private'.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for organisation and search.",
                },
            },
            "required": ["title", "path", "content"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        title = call.arguments.get("title", "")
        path = call.arguments.get("path", "")
        content = call.arguments.get("content", "")
        scope = call.arguments.get("scope", "private")
        tags = call.arguments.get("tags") or []
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            item = await svc.create_item(
                path=path, title=title, content=content, scope=scope, tags=tags
            )
            return make_result(
                call,
                f"Workspace item '{title}' created (id: {item.id}, path: {item.path}, scope: {item.scope}).",
            )
        except Exception as e:
            return fail(call, f"Failed to create workspace item: {e}")


class DeleteWorkspaceItemTool:
    definition = ToolDef(
        name="delete_workspace_item",
        description=(
            "Soft-delete a workspace item by ID. The item is marked as deleted "
            "and will no longer appear in listings or be injected into agent context. "
            "Use list_workspace_items to find the item ID first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "UUID of the workspace item to delete.",
                },
            },
            "required": ["item_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        item_id = call.arguments.get("item_id", "")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            item = await svc.get_item(item_id)  # raises 404 if not found / not owned
            await svc.delete_item(item_id)
            return make_result(call, f"Workspace item '{item.title}' (path: {item.path}) deleted.")
        except Exception as e:
            return fail(call, f"Failed to delete workspace item: {e}")


class CreateWorkspaceDirectoryTool:
    definition = ToolDef(
        name="create_workspace_directory",
        description=(
            "Create a directory node in the shared workspace to organise files and notes. "
            "Use a logical path like 'reports/2025' or 'templates'. "
            "Directories are structural; they do not hold content themselves."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Logical path of the directory, e.g. 'reports/2025'.",
                },
                "title": {
                    "type": "string",
                    "description": "Human-readable label for the directory.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["private", "org", "project"],
                    "description": "Visibility scope. Defaults to 'private'.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags.",
                },
            },
            "required": ["path", "title"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        path = call.arguments.get("path", "")
        title = call.arguments.get("title", "")
        scope = call.arguments.get("scope", "private")
        tags = call.arguments.get("tags") or []
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            item = await svc.create_directory(path=path, title=title, scope=scope, tags=tags)
            return make_result(
                call,
                f"Workspace directory '{title}' created (id: {item.id}, path: {item.path}).",
            )
        except Exception as e:
            return fail(call, f"Failed to create workspace directory: {e}")


class ReadWorkspaceFileTool:
    definition = ToolDef(
        name="read_workspace_file",
        description=(
            "Read the text content of a workspace file item by its ID. "
            "Only suitable for text-based files (plain text, markdown, JSON, XML, etc.). "
            "Use list_workspace_items first to find the file's ID."
        ),
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "UUID of the workspace file item.",
                },
                "encoding": {
                    "type": "string",
                    "description": "Text encoding. Defaults to 'utf-8'.",
                },
            },
            "required": ["item_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        item_id = call.arguments.get("item_id", "")
        encoding = call.arguments.get("encoding", "utf-8")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            content_bytes, mime_type = await svc.get_file_content(item_id)
            try:
                text = content_bytes.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                return fail(call, f"File is not readable as text with encoding '{encoding}'.")
            return make_result(call, f"[{mime_type}]\n{text}")
        except Exception as e:
            return fail(call, f"Failed to read workspace file: {e}")


class MoveWorkspaceItemTool:
    definition = ToolDef(
        name="move_workspace_item",
        description=(
            "Move or rename a workspace item (note, file, or directory) to a new path. "
            "For files, the underlying file is also moved on disk. "
            "Provide only new_path; new_title is optional."
        ),
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "UUID of the workspace item to move.",
                },
                "new_path": {
                    "type": "string",
                    "description": "New logical path, e.g. 'archive/old-report.pdf'.",
                },
                "new_title": {
                    "type": "string",
                    "description": "Optional new title.",
                },
            },
            "required": ["item_id", "new_path"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        item_id = call.arguments.get("item_id", "")
        new_path = call.arguments.get("new_path", "")
        new_title = call.arguments.get("new_title")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            item = await svc.move_item(item_id, new_path, new_title)
            return make_result(
                call,
                f"Workspace item moved to '{item.path}' (title: '{item.title}', version: {item.version}).",
            )
        except Exception as e:
            return fail(call, f"Failed to move workspace item: {e}")


class UpdateWorkspaceItemTool:
    definition = ToolDef(
        name="update_workspace_item",
        description=(
            "Update an existing workspace item. A version snapshot is saved automatically "
            "before the update. Provide only the fields you want to change."
        ),
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "UUID of the workspace item to update.",
                },
                "title": {"type": "string", "description": "New title (optional)."},
                "path": {"type": "string", "description": "New logical path (optional)."},
                "content": {"type": "string", "description": "New markdown content (optional)."},
                "scope": {
                    "type": "string",
                    "enum": ["private", "org", "project"],
                    "description": "New scope (optional).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New tag list (optional, replaces existing tags).",
                },
            },
            "required": ["item_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        item_id = call.arguments.get("item_id", "")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        fields = {k: v for k, v in call.arguments.items() if k != "item_id" and v is not None}

        if not fields:
            return fail(call, "No fields provided to update.")

        try:
            from domains.workspace.workspace_service import WorkspaceService

            svc = WorkspaceService(db, user_id)
            item = await svc.update_item(item_id, **fields)
            return make_result(
                call,
                f"Workspace item '{item.title}' updated to version {item.version}.",
            )
        except Exception as e:
            return fail(call, f"Failed to update workspace item: {e}")

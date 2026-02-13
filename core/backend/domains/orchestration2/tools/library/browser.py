"""Browser automation tools: open, click, fill, screenshot."""

from __future__ import annotations

import uuid

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_project_id, get_user_id, make_result
from shared.paths import get_project_dir, secure_path_join


class BrowserOpenTool:
    definition = ToolDef(
        name="browser_open",
        description="Opens a URL in the browser and returns the page title and content summary.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to open"},
                "wait_until": {"type": "string", "description": "Navigation event: load, domcontentloaded, networkidle"},
            },
            "required": ["url"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        url = call.arguments.get("url", "")
        wait_until = call.arguments.get("wait_until", "networkidle")

        try:
            from shared.browser_manager import browser_manager

            session_id = get_project_id(ctx)
            page = await browser_manager.get_page(session_id)
            await page.goto(url, wait_until=wait_until)

            title = await page.title()
            content = await page.evaluate("() => document.body.innerText.substring(0, 5000)")

            return make_result(
                call,
                f"Opened {url}. Title: {title}\n\nContent Summary:\n{content}...",
            )
        except Exception as e:
            return fail(call, f"Failed to open {url}: {e}")


class BrowserClickTool:
    definition = ToolDef(
        name="browser_click",
        description="Clicks an element on the current page using a CSS selector or text.",
        parameters={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector or text of the element"},
                "timeout": {"type": "integer", "description": "Max wait time in ms"},
            },
            "required": ["selector"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        selector = call.arguments.get("selector", "")
        timeout = call.arguments.get("timeout", 30000)

        try:
            from shared.browser_manager import browser_manager

            session_id = get_project_id(ctx)
            page = await browser_manager.get_page(session_id)
            try:
                await page.click(selector, timeout=timeout)
            except Exception:
                await page.get_by_text(selector).click(timeout=timeout)

            return make_result(call, f"Clicked '{selector}'.")
        except Exception as e:
            return fail(call, f"Failed to click '{selector}': {e}")


class BrowserFillTool:
    definition = ToolDef(
        name="browser_fill",
        description="Fills an input field with the specified value.",
        parameters={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the input field"},
                "value": {"type": "string", "description": "Text to fill"},
            },
            "required": ["selector", "value"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        selector = call.arguments.get("selector", "")
        value = call.arguments.get("value", "")

        try:
            from shared.browser_manager import browser_manager

            session_id = get_project_id(ctx)
            page = await browser_manager.get_page(session_id)
            await page.fill(selector, value)
            return make_result(call, f"Filled '{selector}' with value.")
        except Exception as e:
            return fail(call, f"Failed to fill '{selector}': {e}")


class BrowserScreenshotTool:
    definition = ToolDef(
        name="browser_screenshot",
        description="Takes a screenshot of the current page.",
        parameters={
            "type": "object",
            "properties": {
                "full_page": {"type": "boolean", "description": "Take full page screenshot"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        full_page = call.arguments.get("full_page", False)

        try:
            from shared.browser_manager import browser_manager

            user_id = get_user_id(ctx)
            project_id = get_project_id(ctx)
            session_id = project_id

            page = await browser_manager.get_page(session_id)

            root_dir = get_project_dir(user_id, project_id)
            browser_dir = secure_path_join(root_dir, "artifacts", "browser")
            browser_dir.mkdir(parents=True, exist_ok=True)

            filename = f"screenshot_{uuid.uuid4().hex[:8]}.png"
            filepath = browser_dir / filename
            await page.screenshot(path=str(filepath), full_page=full_page)

            rel_path = filepath.relative_to(root_dir).as_posix()
            return make_result(call, f"Screenshot taken: {rel_path}")
        except Exception as e:
            return fail(call, f"Failed to take screenshot: {e}")

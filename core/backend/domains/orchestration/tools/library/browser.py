import logging
import os
import uuid
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field
from domains.orchestration.tools.base import BaseTool, IntegrationContext, ToolResult, ToolAttachment
from domains.orchestration.browser_manager import browser_manager
from shared.paths import get_project_dir, secure_path_join

logger = logging.getLogger(__name__)

class BrowserOpenArgs(BaseModel):
    url: str = Field(..., description="The URL to open in the browser.")
    wait_until: Optional[str] = Field("networkidle", description="When to consider navigation finished: 'load', 'domcontentloaded', 'networkidle', 'commit'.")

class BrowserOpenTool(BaseTool):
    name = "browser_open"
    description = "Opens a specified URL in the browser and returns the page title and a summary of the content."
    args_schema = BrowserOpenArgs

    async def run(self, ctx: IntegrationContext, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id") or ctx.project_id or "default"
        url = kwargs.get("url")
        wait_until = kwargs.get("wait_until", "networkidle")

        try:
            page = await browser_manager.get_page(session_id)
            await self.report_status(f"Opening URL: {url}...")
            await page.goto(url, wait_until=wait_until)
            
            title = await page.title()
            # Extract basic text content for the LLM
            content = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
            
            return ToolResult(
                content=f"Successfully opened {url}. Page Title: {title}\n\nContent Summary:\n{content}...",
                data={"url": url, "title": title}
            )
        except Exception as e:
            logger.error(f"Error in browser_open: {e}")
            return ToolResult(content=f"Failed to open {url}: {str(e)}", is_success=False)

class BrowserClickArgs(BaseModel):
    selector: str = Field(..., description="The CSS selector or text of the element to click.")
    timeout: Optional[int] = Field(30000, description="Maximum time to wait for the element in milliseconds.")

class BrowserClickTool(BaseTool):
    name = "browser_click"
    description = "Clicks an element on the current page using a CSS selector or text."
    args_schema = BrowserClickArgs

    async def run(self, ctx: IntegrationContext, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id") or ctx.project_id or "default"
        selector = kwargs.get("selector")
        timeout = kwargs.get("timeout", 30000)

        try:
            page = await browser_manager.get_page(session_id)
            await self.report_status(f"Clicking: {selector}...")
            
            # Attempt to click by selector, if it fails, try by text
            try:
                await page.click(selector, timeout=timeout)
            except:
                await page.get_by_text(selector).click(timeout=timeout)
                
            return ToolResult(content=f"Successfully clicked '{selector}'.")
        except Exception as e:
            return ToolResult(content=f"Failed to click '{selector}': {str(e)}", is_success=False)

class BrowserFillArgs(BaseModel):
    selector: str = Field(..., description="The CSS selector of the input field.")
    value: str = Field(..., description="The text to fill into the input field.")

class BrowserFillTool(BaseTool):
    name = "browser_fill"
    description = "Fills an input field with the specified value."
    args_schema = BrowserFillArgs

    async def run(self, ctx: IntegrationContext, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id") or ctx.project_id or "default"
        selector = kwargs.get("selector")
        value = kwargs.get("value")

        try:
            page = await browser_manager.get_page(session_id)
            await self.report_status(f"Filling {selector} with value...")
            await page.fill(selector, value)
            return ToolResult(content=f"Successfully filled '{selector}' with value.")
        except Exception as e:
            return ToolResult(content=f"Failed to fill '{selector}': {str(e)}", is_success=False)

class BrowserScreenshotArgs(BaseModel):
    full_page: Optional[bool] = Field(False, description="Whether to take a full page screenshot.")

class BrowserScreenshotTool(BaseTool):
    name = "browser_screenshot"
    description = "Takes a screenshot of the current page and returns it to the agent."
    args_schema = BrowserScreenshotArgs

    async def run(self, ctx: IntegrationContext, **kwargs) -> ToolResult:
        session_id = kwargs.get("session_id") or ctx.project_id or "default"
        full_page = kwargs.get("full_page", False)

        try:
            page = await browser_manager.get_page(session_id)
            await self.report_status("Taking screenshot...")
            
            # Define output path: user_projects_dir/{project}/artifacts/browser/
            root_dir = get_project_dir(ctx.user_id, ctx.project_id)
            browser_artifacts_dir = secure_path_join(root_dir, "artifacts", "browser")
            browser_artifacts_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"screenshot_{uuid.uuid4().hex[:8]}.png"
            filepath = browser_artifacts_dir / filename
            
            await page.screenshot(path=str(filepath), full_page=full_page)
            
            # Convert to relative path for return
            rel_path = filepath.relative_to(root_dir).as_posix()
            
            # Upload to Gemini if possible
            # We need an AI Provider for this.
            # In VisionArk, we usually return the path and let the system handle it, 
            # or upload it immediately if we have a provider.
            
            # Better approach: return a ToolAttachment that the ReasoningEngine/Provider can handle.
            # Since we want Gemini to see this, we should ideally upload it to Gemini File API.
            
            # Check if we can get the provider from context or meta
            api_key = ctx.meta.get("api_key")
            if api_key:
                from infrastructure.llm import get_provider
                provider = get_provider(api_key=api_key)
                if hasattr(provider, "upload_file"):
                    upload_res = await provider.upload_file(str(filepath), mime_type="image/png", display_name=f"Screenshot {session_id}")
                    gemini_uri = upload_res.get("file_uri")
                    
                    return ToolResult(
                        content=f"Screenshot taken and uploaded to Gemini. File path: {rel_path}",
                        attachments=[ToolAttachment(type="gemini_file_uri", value=gemini_uri, mime_type="image/png")]
                    )

            return ToolResult(
                content=f"Screenshot taken. File path: {rel_path}",
                attachments=[ToolAttachment(type="image_path", value=str(filepath), mime_type="image/png")],
                data={"path": rel_path}
            )
        except Exception as e:
            return ToolResult(content=f"Failed to take screenshot: {str(e)}", is_success=False)

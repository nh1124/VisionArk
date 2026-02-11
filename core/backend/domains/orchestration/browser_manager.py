import asyncio
import logging
from typing import Dict, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages Playwright browser instances and contexts.
    Ensures isolated contexts for each user/session for multi-user safety.
    """
    _instance: Optional['BrowserManager'] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.contexts: Dict[str, BrowserContext] = {}
        self.initialized = True

    async def start(self):
        """Initialize Playwright and launch the browser if not already started."""
        async with self._lock:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=True)
                logger.info("Playwright browser launched.")

    async def get_context(self, session_id: str) -> BrowserContext:
        """Get or create an isolated BrowserContext for the given session."""
        if not self.browser:
            await self.start()
        
        async with self._lock:
            if session_id not in self.contexts:
                context = await self.browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
                )
                self.contexts[session_id] = context
                logger.info(f"Created new BrowserContext for session: {session_id}")
            return self.contexts[session_id]

    async def get_page(self, session_id: str) -> Page:
        """Get the active page for a session, or create one if none exists."""
        context = await self.get_context(session_id)
        pages = context.pages
        if not pages:
            page = await context.new_page()
            logger.info(f"Created new Page for session: {session_id}")
            return page
        return pages[0]

    async def close_context(self, session_id: str):
        """Close the BrowserContext for a specific session."""
        async with self._lock:
            context = self.contexts.pop(session_id, None)
            if context:
                await context.close()
                logger.info(f"Closed BrowserContext for session: {session_id}")

    async def shutdown(self):
        """Shutdown Playwright and close the browser."""
        async with self._lock:
            for context in self.contexts.values():
                await context.close()
            self.contexts.clear()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.playwright = None
            self.browser = None
            logger.info("Playwright shutdown complete.")

# Global instance for easy access
browser_manager = BrowserManager()

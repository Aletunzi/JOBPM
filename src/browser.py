"""
Browser management: Playwright setup with stealth and persistent context.
"""

import os
import logging
from pathlib import Path

import yaml
from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import stealth_async

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


async def create_browser_context(playwright, config: dict | None = None) -> BrowserContext:
    """Create a persistent browser context with stealth applied.

    On first run the browser opens in headed mode so the user can log in
    manually.  Subsequent runs reuse the saved cookies/state.
    """
    if config is None:
        config = load_config()

    browser_cfg = config.get("browser", {})
    state_dir = Path(__file__).resolve().parent.parent / browser_cfg.get("state_dir", "data/browser_state")
    state_dir.mkdir(parents=True, exist_ok=True)

    first_run = not any(state_dir.iterdir())

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(state_dir),
        headless=False if first_run else browser_cfg.get("headless", True),
        viewport={
            "width": browser_cfg.get("viewport_width", 1920),
            "height": browser_cfg.get("viewport_height", 1080),
        },
        user_agent=browser_cfg.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ),
        locale="en-US",
        timezone_id="Europe/Rome",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
        ],
    )

    # Apply stealth to every page in the context
    for page in context.pages:
        await stealth_async(page)

    context.on("page", lambda page: stealth_async(page))

    if first_run:
        logger.info(
            "First run detected — browser opened in headed mode. "
            "Please log in to X manually, then close the browser."
        )

    return context


async def get_page(context: BrowserContext) -> Page:
    """Return the first existing page or create a new one."""
    if context.pages:
        page = context.pages[0]
    else:
        page = await context.new_page()
    await stealth_async(page)
    return page


class BrowserManager:
    """Async context manager for the browser lifecycle."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self._playwright = None
        self._context = None

    async def __aenter__(self) -> "BrowserManager":
        self._playwright = await async_playwright().start()
        self._context = await create_browser_context(self._playwright, self.config)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def context(self) -> BrowserContext:
        return self._context

    async def page(self) -> Page:
        return await get_page(self._context)

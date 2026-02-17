"""
Browser management: Playwright setup with stealth and persistent context.
"""

import os
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv
from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import stealth_async, StealthConfig

# Load .env early — before any credential access
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


async def create_browser_context(playwright, config: dict | None = None) -> BrowserContext:
    """Create a persistent browser context with stealth applied.

    On first run, performs automated login using credentials from
    environment variables.  Subsequent runs reuse saved cookies/state.
    """
    if config is None:
        config = load_config()

    browser_cfg = config.get("browser", {})
    state_dir = Path(__file__).resolve().parent.parent / browser_cfg.get("state_dir", "data/browser_state")
    state_dir.mkdir(parents=True, exist_ok=True)

    headless = browser_cfg.get("headless", True)

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(state_dir),
        headless=headless,
        viewport={
            "width": browser_cfg.get("viewport_width", 1920),
            "height": browser_cfg.get("viewport_height", 1080),
        },
        user_agent=browser_cfg.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        ),
        locale="en-US",
        timezone_id="Europe/Rome",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
        ],
    )

    # Minimal stealth config — only essential scripts to avoid X detecting
    # "privacy extensions" and blocking the page
    stealth_cfg = StealthConfig(
        webdriver=True,
        chrome_app=False,
        chrome_csi=False,
        chrome_load_times=False,
        chrome_runtime=False,
        iframe_content_window=False,
        media_codecs=False,
        navigator_hardware_concurrency=4,
        navigator_languages=False,
        navigator_permissions=False,
        navigator_platform=False,
        navigator_plugins=False,
        navigator_user_agent=False,
        navigator_vendor=False,
        outerdimensions=False,
        hairline=False,
        webgl_vendor=False,
    )

    # Apply stealth to every page in the context
    for page in context.pages:
        await stealth_async(page, stealth_cfg)

    context.on("page", lambda page: stealth_async(page, stealth_cfg))

    # Auto-login if not authenticated
    from src.auth import get_credentials, is_logged_in, perform_login

    page = context.pages[0] if context.pages else await context.new_page()
    await stealth_async(page, stealth_cfg)

    if not await is_logged_in(page):
        logger.info("Not logged in — attempting automated login.")
        creds = get_credentials()
        success = await perform_login(page, creds)
        if not success:
            raise RuntimeError(
                "Automated login failed. Check credentials in .env file."
            )
        # Save state after successful login
        await context.storage_state(path=str(state_dir / "storage_state.json"))
        logger.info("Login state saved to persistent context.")

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

"""
Automated X (Twitter) login using credentials from environment variables.
Credentials are NEVER logged or stored in code.
"""

import os
import logging

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.anti_detection import click_element_human, human_delay, type_human_into_element

logger = logging.getLogger(__name__)


def _mask(value: str) -> str:
    """Return a masked version of a credential for safe logging."""
    if not value or len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def get_credentials() -> dict:
    """Load credentials from environment variables.

    Raises EnvironmentError if required variables are missing.
    """
    username = os.environ.get("X_USERNAME", "").strip()
    email = os.environ.get("X_EMAIL", "").strip()
    password = os.environ.get("X_PASSWORD", "").strip()

    if not username or not password:
        raise EnvironmentError(
            "X_USERNAME and X_PASSWORD must be set in the .env file or environment."
        )

    logger.info("Credentials loaded for user %s", _mask(username))
    return {"username": username, "email": email, "password": password}


async def is_logged_in(page: Page) -> bool:
    """Check if the current session is already authenticated on X."""
    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded")
        await human_delay(3, 5)

        # If we land on the home timeline, we're logged in
        home_timeline = page.locator('[data-testid="primaryColumn"]')
        if await home_timeline.is_visible(timeout=5000):
            # Extra check: make sure we're not on the login/signup page
            url = page.url.lower()
            if "login" not in url and "i/flow" not in url:
                logger.info("Session is authenticated — skipping login.")
                return True
    except PlaywrightTimeout:
        pass

    return False


async def perform_login(page: Page, credentials: dict) -> bool:
    """Perform automated login to X using the provided credentials.

    Returns True if login succeeded.
    """
    logger.info("Starting automated login flow...")

    # Navigate to login page
    await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded")
    await human_delay(3, 5)

    # Handle "Something went wrong" error page — click "Try again" up to 3 times
    for attempt in range(3):
        try_again = page.locator('text="Try again"')
        try:
            if await try_again.is_visible(timeout=3000):
                logger.warning("X showed 'Something went wrong' — clicking Try again (attempt %d)", attempt + 1)
                await try_again.click()
                await human_delay(3, 5)
            else:
                break
        except PlaywrightTimeout:
            break

    # --- Step 1: Enter username/email ---
    username_input = page.locator('input[autocomplete="username"]')
    try:
        await username_input.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeout:
        # Debug: save screenshot and page URL to understand what X is showing
        debug_path = "data/debug_login.png"
        try:
            await page.screenshot(path=debug_path, full_page=True)
            logger.error("Login page did not load — screenshot saved to %s", debug_path)
            logger.error("Current URL: %s", page.url)
            logger.error("Page title: %s", await page.title())
        except Exception as e:
            logger.error("Could not save debug screenshot: %s", e)
        logger.error("Login page did not load — username input not found.")
        return False

    # Click input field and type with real keyboard events (fill() is ignored by X's React form)
    await username_input.click()
    await human_delay(0.3, 0.5)
    await page.keyboard.type(credentials["email"], delay=50)
    logger.info("Email typed via keyboard.")
    await human_delay(1.0, 2.0)

    # Take a screenshot after typing to verify
    try:
        await page.screenshot(path="data/debug_after_email.png", full_page=True)
    except Exception:
        pass

    # Click "Next"
    next_btn = page.locator('button:has-text("Next")')
    await next_btn.click()
    logger.info("Clicked Next.")
    await human_delay(3, 5)

    # Take screenshot after Next to see what page we're on
    try:
        await page.screenshot(path="data/debug_after_next.png", full_page=True)
    except Exception:
        pass

    # --- Step 2: Handle possible username verification step ---
    unusual_input = page.locator('[data-testid="ocfEnterTextTextInput"]')
    try:
        if await unusual_input.is_visible(timeout=5000):
            logger.info("X requested additional username verification.")
            await unusual_input.click()
            await human_delay(0.3, 0.5)
            await page.keyboard.type(credentials["username"], delay=50)
            await human_delay(0.5, 1.0)
            next_btn2 = page.locator('[data-testid="ocfEnterTextNextButton"]')
            await next_btn2.click()
            await human_delay(3, 5)
    except PlaywrightTimeout:
        pass

    # --- Step 3: Enter password ---
    password_input = page.locator('input[type="password"]')
    try:
        await password_input.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeout:
        debug_path = "data/debug_password.png"
        try:
            await page.screenshot(path=debug_path, full_page=True)
            logger.error("Password input not found — screenshot saved to %s", debug_path)
            logger.error("Current URL: %s", page.url)
        except Exception as e:
            logger.error("Could not save debug screenshot: %s", e)
        logger.error("Password input not found — login flow may have changed.")
        return False

    await password_input.click()
    await human_delay(0.3, 0.5)
    await page.keyboard.type(credentials["password"], delay=50)
    logger.info("Password typed via keyboard.")
    await human_delay(0.5, 1.0)

    # Click "Log in"
    login_btn = page.locator('[data-testid="LoginForm_Login_Button"]')
    await login_btn.click()
    logger.info("Clicked Log in.")
    await human_delay(3, 5)

    # --- Step 4: Verify login success ---
    # Check if we landed on the home timeline
    try:
        home_timeline = page.locator('[data-testid="primaryColumn"]')
        await home_timeline.wait_for(state="visible", timeout=15000)

        url = page.url.lower()
        if "login" not in url and "i/flow" not in url:
            logger.info("Login successful.")
            return True
    except PlaywrightTimeout:
        pass

    # Check for error messages
    error_msg = page.locator('[data-testid="inline_message"]')
    try:
        if await error_msg.is_visible(timeout=2000):
            text = await error_msg.text_content()
            logger.error("Login failed with error: %s", text)
    except PlaywrightTimeout:
        pass

    logger.error("Login verification failed — could not confirm authenticated state.")
    return False

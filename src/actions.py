"""
Core actions: search for profiles, navigate to verified followers, follow users.
Includes rate-limit and captcha detection.
"""

import logging
import random

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.anti_detection import (
    click_element_human,
    follow_cooldown,
    human_delay,
    profile_switch_cooldown,
    scroll_down_natural,
    type_human,
)
from src.session_tracker import SessionRecord

logger = logging.getLogger(__name__)

X_BASE = "https://x.com"

# --- Rate-limit / block detection ---------------------------------------------------


class RateLimitError(Exception):
    """Raised when X shows a rate-limit message."""
    pass


class CaptchaError(Exception):
    """Raised when X presents a captcha challenge."""
    pass


async def check_for_rate_limit(page: Page) -> None:
    """Inspect the page for rate-limit banners or error messages."""
    rate_limit_signals = [
        "text=Rate limit exceeded",
        "text=You are over the daily limit",
        "text=Try again later",
        "text=Something went wrong. Try reloading",
        "text=Cannot follow any more people at this time",
    ]
    for selector in rate_limit_signals:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=500):
                msg = await el.text_content()
                raise RateLimitError(f"Rate limit detected: {msg}")
        except PlaywrightTimeout:
            continue


async def check_for_captcha(page: Page) -> None:
    """Detect captcha/challenge pages."""
    captcha_signals = [
        "iframe[src*='captcha']",
        "iframe[src*='challenge']",
        "[data-testid='ocfEnterTextTextInput']",
    ]
    for selector in captcha_signals:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=500):
                raise CaptchaError("Captcha/challenge page detected")
        except PlaywrightTimeout:
            continue


async def safety_checks(page: Page) -> None:
    """Run all safety checks on the current page."""
    await check_for_rate_limit(page)
    await check_for_captcha(page)


# --- Navigation helpers --------------------------------------------------------------


async def go_to_x_home(page: Page) -> None:
    """Navigate to X home, wait for load."""
    await page.goto(X_BASE, wait_until="domcontentloaded")
    await human_delay(2, 4)
    await safety_checks(page)


async def search_profile(page: Page, handle: str) -> None:
    """Use the search bar to navigate to a profile."""
    logger.info("Searching for profile: @%s", handle)

    # Click the search box in the top nav
    search_box = page.locator('[data-testid="SearchBox_Search_Input"]')

    # If search box not visible, click the Explore tab first
    if not await search_box.is_visible(timeout=2000):
        explore_link = page.locator('a[data-testid="AppTabBar_Explore_Link"]')
        if await explore_link.is_visible(timeout=2000):
            await click_element_human(page, explore_link)
            await human_delay(1.5, 3)
        search_box = page.locator('[data-testid="SearchBox_Search_Input"]')

    await search_box.wait_for(state="visible", timeout=10000)

    # Clear existing text and type the handle
    await click_element_human(page, search_box)
    await human_delay(0.3, 0.6)
    await page.keyboard.press("Control+a")
    await human_delay(0.1, 0.3)

    # Type handle with human-like timing
    for i, char in enumerate(handle):
        await page.keyboard.type(char)
        delay_base = random.gauss(0.12, 0.04)
        delay = max(0.08, min(0.25, delay_base))
        if i > 0 and i % random.randint(3, 6) == 0:
            delay += random.uniform(0.2, 0.5)
        import asyncio
        await asyncio.sleep(delay)

    await human_delay(0.8, 1.5)
    await page.keyboard.press("Enter")
    await human_delay(2, 4)
    await safety_checks(page)


async def navigate_to_profile(page: Page, handle: str) -> bool:
    """From search results, click through to the profile page.

    Returns True if we successfully land on the profile.
    """
    # After searching, look for the "People" tab to filter results
    people_tab = page.locator('[role="tab"]:has-text("People")')
    if await people_tab.is_visible(timeout=3000):
        await click_element_human(page, people_tab)
        await human_delay(1.5, 3)

    # Find the profile link in the results
    profile_link = page.locator(f'a[href="/{handle}" i]').first
    if not await profile_link.is_visible(timeout=5000):
        # Try clicking the first user cell as fallback
        user_cell = page.locator('[data-testid="UserCell"]').first
        if await user_cell.is_visible(timeout=3000):
            await click_element_human(page, user_cell)
        else:
            logger.warning("Could not find profile @%s in search results", handle)
            return False
    else:
        await click_element_human(page, profile_link)

    await human_delay(2, 4)
    await safety_checks(page)

    # Verify we are on the correct profile page
    current_url = page.url.lower()
    if handle.lower() in current_url:
        logger.info("Landed on profile page: @%s", handle)
        return True

    logger.warning("URL mismatch after navigation: %s (expected @%s)", page.url, handle)
    return True  # proceed anyway, the profile link click was successful


async def go_to_verified_followers(page: Page, handle: str) -> bool:
    """From a profile page, navigate to the Verified Followers tab.

    Returns True if successful.
    """
    # Click on "Followers" link
    followers_link = page.locator(f'a[href="/{handle}/followers" i]')
    if not await followers_link.is_visible(timeout=5000):
        # Fallback: find any element that says "Followers"
        followers_link = page.locator('a:has-text("Followers")').first
    if not await followers_link.is_visible(timeout=5000):
        logger.warning("Could not find Followers link for @%s", handle)
        return False

    await click_element_human(page, followers_link)
    await human_delay(2, 4)
    await safety_checks(page)

    # Click on "Verified Followers" tab
    verified_tab = page.locator('[role="tab"]:has-text("Verified")')
    if not await verified_tab.is_visible(timeout=5000):
        # Alternative: try the direct URL
        await page.goto(f"{X_BASE}/{handle}/verified_followers", wait_until="domcontentloaded")
        await human_delay(2, 4)
    else:
        await click_element_human(page, verified_tab)
        await human_delay(2, 4)

    await safety_checks(page)
    logger.info("On verified followers page for @%s", handle)
    return True


# --- Follow logic ---------------------------------------------------------------------


async def _get_follow_button_state(user_cell) -> str | None:
    """Return 'follow' or 'following' based on the button inside a UserCell."""
    # The follow/following button inside each user cell
    btn = user_cell.locator('[data-testid$="-follow"]').first
    if await btn.is_visible(timeout=1000):
        label = await btn.get_attribute("aria-label") or ""
        text = (await btn.text_content() or "").strip().lower()
        if "following" in label.lower() or text == "following":
            return "following"
        if "follow" in label.lower() or text == "follow":
            return "follow"
    return None


async def _get_username_from_cell(user_cell) -> str:
    """Extract the @username from a UserCell."""
    link = user_cell.locator('a[role="link"][href^="/"]').first
    href = await link.get_attribute("href") or ""
    return href.strip("/").split("/")[0] if href else "unknown"


async def follow_verified_followers(
    page: Page,
    handle: str,
    max_follows: int,
    record: SessionRecord,
    config: dict,
) -> int:
    """Scroll through the verified followers list and follow up to max_follows users.

    Returns the number of follows performed.
    """
    follows_done = 0
    seen_usernames: set[str] = set()
    scroll_attempts_without_new = 0
    max_scroll_attempts = 15

    limits = config.get("limits", {})
    follow_delay_min = limits.get("follow_delay_min", 15)
    follow_delay_max = limits.get("follow_delay_max", 45)

    while follows_done < max_follows and scroll_attempts_without_new < max_scroll_attempts:
        await safety_checks(page)

        user_cells = page.locator('[data-testid="UserCell"]')
        count = await user_cells.count()

        new_found = False
        for i in range(count):
            if follows_done >= max_follows:
                break

            cell = user_cells.nth(i)
            username = await _get_username_from_cell(cell)

            if username in seen_usernames:
                continue
            seen_usernames.add(username)
            new_found = True

            state = await _get_follow_button_state(cell)
            if state == "following":
                logger.debug("Already following @%s — skipping", username)
                record.record_skip(username)
                continue

            if state == "follow":
                logger.info("Following @%s (from @%s)", username, handle)
                btn = cell.locator('[data-testid$="-follow"]').first
                await click_element_human(page, btn)
                follows_done += 1
                record.record_follow(username)

                # Check for immediate rate-limit popup after follow
                await human_delay(1, 2)
                await safety_checks(page)

                if follows_done < max_follows:
                    await follow_cooldown(follow_delay_min, follow_delay_max)

        if not new_found:
            scroll_attempts_without_new += 1
        else:
            scroll_attempts_without_new = 0

        if follows_done < max_follows:
            await scroll_down_natural(page, random.randint(300, 600))
            await human_delay(1, 2)

    logger.info("Finished @%s — followed %d users", handle, follows_done)
    return follows_done


# --- Full session orchestration -------------------------------------------------------


async def run_session(page: Page, config: dict, record: SessionRecord) -> None:
    """Execute one complete follow session across all target profiles."""
    profiles = config.get("target_profiles", [])
    limits = config.get("limits", {})
    max_per_profile = limits.get("max_follows_per_profile", 6)
    profile_delay_min = limits.get("profile_switch_delay_min", 60)
    profile_delay_max = limits.get("profile_switch_delay_max", 180)

    await go_to_x_home(page)

    for idx, handle in enumerate(profiles):
        logger.info("=== Processing profile %d/%d: @%s ===", idx + 1, len(profiles), handle)
        record.start_profile(handle)

        try:
            await search_profile(page, handle)
            if not await navigate_to_profile(page, handle):
                logger.warning("Skipping @%s — could not navigate to profile", handle)
                record.finish_profile()
                continue

            if not await go_to_verified_followers(page, handle):
                logger.warning("Skipping @%s — could not reach verified followers", handle)
                record.finish_profile()
                continue

            await follow_verified_followers(page, handle, max_per_profile, record, config)

        except RateLimitError as e:
            logger.warning("Rate limit hit on @%s: %s", handle, e)
            record.finish_profile()
            record.finish(status="rate_limited", error=str(e))
            raise
        except CaptchaError as e:
            logger.warning("Captcha detected on @%s: %s", handle, e)
            record.finish_profile()
            record.finish(status="captcha_blocked", error=str(e))
            raise
        except Exception as e:
            logger.error("Unexpected error on @%s: %s", handle, e, exc_info=True)
            record.finish_profile()
            record.finish(status="error", error=str(e))
            raise

        record.finish_profile()

        # Pause between profiles
        if idx < len(profiles) - 1:
            logger.info("Waiting before next profile...")
            await profile_switch_cooldown(profile_delay_min, profile_delay_max)

    record.finish(status="completed")
    logger.info("Session completed — total follows: %d", record.total_follows)

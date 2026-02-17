"""
Anti-detection utilities for human-like browser interaction.
Gaussian delays, Bézier mouse curves, realistic typing, natural scrolling.
"""

import asyncio
import random
import math


def _gauss_clamp(mean: float, std: float, low: float, high: float) -> float:
    """Return a gaussian-distributed random value clamped to [low, high]."""
    value = random.gauss(mean, std)
    return max(low, min(high, value))


async def human_delay(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    """Sleep for a gaussian-distributed random duration."""
    mean = (min_sec + max_sec) / 2
    std = (max_sec - min_sec) / 4
    delay = _gauss_clamp(mean, std, min_sec, max_sec)
    await asyncio.sleep(delay)


async def follow_cooldown(min_sec: float = 15.0, max_sec: float = 45.0) -> None:
    """Longer pause between follow actions."""
    await human_delay(min_sec, max_sec)


async def profile_switch_cooldown(min_sec: float = 60.0, max_sec: float = 180.0) -> None:
    """Pause between switching target profiles."""
    await human_delay(min_sec, max_sec)


# ---------------------------------------------------------------------------
# Bézier mouse movement
# ---------------------------------------------------------------------------

def _bezier_point(t: float, p0: tuple, p1: tuple, p2: tuple, p3: tuple) -> tuple:
    """Compute a point on a cubic Bézier curve at parameter t."""
    u = 1 - t
    x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
    return (int(x), int(y))


def _generate_bezier_path(start: tuple, end: tuple, steps: int = 25) -> list[tuple]:
    """Generate a list of points along a Bézier curve from start to end."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    # Control points with randomized offsets for natural curvature
    cp1 = (
        start[0] + dx * random.uniform(0.2, 0.4) + random.randint(-50, 50),
        start[1] + dy * random.uniform(0.0, 0.3) + random.randint(-50, 50),
    )
    cp2 = (
        start[0] + dx * random.uniform(0.6, 0.8) + random.randint(-50, 50),
        start[1] + dy * random.uniform(0.7, 1.0) + random.randint(-50, 50),
    )

    points = []
    for i in range(steps + 1):
        t = i / steps
        points.append(_bezier_point(t, start, cp1, cp2, end))
    return points


async def move_mouse_human(page, target_x: int, target_y: int) -> None:
    """Move the mouse to (target_x, target_y) along a Bézier curve."""
    # Get current mouse position (default to a random starting point)
    start_x = random.randint(100, 400)
    start_y = random.randint(100, 400)

    steps = random.randint(18, 35)
    path = _generate_bezier_path((start_x, start_y), (target_x, target_y), steps)

    for point in path:
        await page.mouse.move(point[0], point[1])
        await asyncio.sleep(random.uniform(0.005, 0.02))


async def click_element_human(page, element) -> None:
    """Move mouse to an element with Bézier curve, then click."""
    box = await element.bounding_box()
    if not box:
        await element.click()
        return

    # Click at a slightly randomized position within the element
    target_x = int(box["x"] + box["width"] * random.uniform(0.3, 0.7))
    target_y = int(box["y"] + box["height"] * random.uniform(0.3, 0.7))

    await move_mouse_human(page, target_x, target_y)
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.click(target_x, target_y)


# ---------------------------------------------------------------------------
# Realistic typing
# ---------------------------------------------------------------------------

async def type_human(page, selector: str, text: str) -> None:
    """Type text into a field with human-like keystroke timing."""
    element = page.locator(selector)
    await click_element_human(page, element)
    await asyncio.sleep(random.uniform(0.3, 0.7))

    for i, char in enumerate(text):
        await page.keyboard.type(char)
        # Base delay between keystrokes
        delay = _gauss_clamp(0.12, 0.04, 0.08, 0.25)

        # Occasional longer pause (simulates thinking)
        if i > 0 and i % random.randint(3, 6) == 0:
            delay += random.uniform(0.2, 0.6)

        await asyncio.sleep(delay)


async def type_human_into_element(element, text: str, page) -> None:
    """Type text into a specific element with human-like timing."""
    await click_element_human(page, element)
    await asyncio.sleep(random.uniform(0.3, 0.7))

    for i, char in enumerate(text):
        await page.keyboard.type(char)
        delay = _gauss_clamp(0.12, 0.04, 0.08, 0.25)
        if i > 0 and i % random.randint(3, 6) == 0:
            delay += random.uniform(0.2, 0.6)
        await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Natural scrolling
# ---------------------------------------------------------------------------

async def scroll_down_natural(page, distance: int = 300) -> None:
    """Scroll down with variable speed and small pauses, like a human."""
    scrolled = 0
    while scrolled < distance:
        chunk = random.randint(40, 120)
        chunk = min(chunk, distance - scrolled)
        await page.mouse.wheel(0, chunk)
        scrolled += chunk
        await asyncio.sleep(random.uniform(0.05, 0.2))

    # Brief pause after scrolling
    await asyncio.sleep(random.uniform(0.3, 0.8))


async def scroll_to_element(page, element) -> None:
    """Scroll until an element is visible, using natural scroll increments."""
    for _ in range(20):
        if await element.is_visible():
            return
        await scroll_down_natural(page, random.randint(200, 400))
        await asyncio.sleep(random.uniform(0.3, 0.6))

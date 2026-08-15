from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

SCHEDULE_SELECTOR = "#enrolledClassSections_content"
COURSE_SELECTOR = "#enrolledClassSections_content .classAbbreviation"


def load_vanderbilt_schedule(url: str, timeout_ms: int = 180_000) -> str:
    """Open the URL in installed Google Chrome and return the rendered schedule HTML.

    A dedicated persistent profile is used so Vanderbilt login/MFA sessions can
    survive between launches. No password is stored by this application.
    """
    profile = Path.home() / "Library" / "Application Support" / "CalendarManager" / "chrome-profile"
    profile.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel="chrome",
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(COURSE_SELECTOR, timeout=timeout_ms)
            html = page.locator(SCHEDULE_SELECTOR).evaluate("(el) => el.outerHTML")
            return html
        finally:
            context.close()

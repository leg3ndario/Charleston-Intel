"""Shared Playwright lifecycle helpers for the harder scrapers."""
import logging
from contextlib import contextmanager

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

log = logging.getLogger(__name__)

DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


@contextmanager
def browser_context(headless: bool = True, slow_mo: int = 0):
    """Yields a Playwright Page. Auto-closes everything."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        try:
            ctx = browser.new_context(user_agent=DEFAULT_UA, viewport={"width": 1400, "height": 900})
            page = ctx.new_page()
            yield page
        finally:
            browser.close()


def safe_text(locator) -> str:
    try:
        return (locator.text_content() or "").strip()
    except Exception:
        return ""

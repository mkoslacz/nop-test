from __future__ import annotations

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


class BrowserManager:
    """Manages Playwright browser lifecycle. Used as async context manager."""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> BrowserManager:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, *args) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_context(
        self, viewport: tuple[int, int] | None = None
    ) -> BrowserContext:
        opts: dict = {"locale": "pl-PL"}
        if viewport:
            opts["viewport"] = {"width": viewport[0], "height": viewport[1]}
        ctx = await self._browser.new_context(**opts)
        ctx.set_default_timeout(self.timeout)
        return ctx

    async def new_page(
        self, url: str, viewport: tuple[int, int] | None = None
    ) -> Page:
        ctx = await self.new_context(viewport)
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle")
        return page

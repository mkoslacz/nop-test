from __future__ import annotations

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType

RESPONSIVE_CHECK_JS = """() => {
    const docWidth = document.documentElement.clientWidth;
    const scrollWidth = document.documentElement.scrollWidth;
    const hasHorizontalOverflow = scrollWidth > docWidth;

    // Check images
    const images = [...document.querySelectorAll('img')];
    const oversizedImages = images
        .filter(img => img.naturalWidth > 0 && img.offsetWidth > docWidth)
        .map(img => ({
            src: img.src?.substring(0, 200),
            naturalWidth: img.naturalWidth,
            displayWidth: img.offsetWidth,
            alt: img.alt?.substring(0, 50) || '',
        }));

    // Check for mobile menu (hamburger)
    const hamburgerSelectors = [
        '.hamburger', '.menu-toggle', '.nav-toggle',
        '[class*="burger"]', '[class*="mobile-menu"]',
        '[aria-label="menu"]', '[aria-label="Menu"]',
        'button[class*="toggle"]',
    ];
    let mobileMenuFound = false;
    for (const sel of hamburgerSelectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) {
            mobileMenuFound = true;
            break;
        }
    }

    // Check text readability (font sizes)
    const textElements = document.querySelectorAll('p, span, a, li, td, th, label');
    let tooSmallText = 0;
    for (const el of textElements) {
        const style = window.getComputedStyle(el);
        const fontSize = parseFloat(style.fontSize);
        if (fontSize < 12 && el.textContent?.trim().length > 0 && el.offsetParent !== null) {
            tooSmallText++;
        }
    }

    // Check touch targets (interactive elements too small)
    const interactive = document.querySelectorAll('a, button, input, select, textarea');
    let smallTouchTargets = 0;
    for (const el of interactive) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0 &&
            (rect.width < 44 || rect.height < 44) &&
            el.offsetParent !== null) {
            smallTouchTargets++;
        }
    }

    return {
        viewport_width: docWidth,
        scroll_width: scrollWidth,
        has_horizontal_overflow: hasHorizontalOverflow,
        overflow_amount: hasHorizontalOverflow ? scrollWidth - docWidth : 0,
        oversized_images: oversizedImages,
        mobile_menu_found: mobileMenuFound,
        too_small_text_count: tooSmallText,
        small_touch_targets: smallTouchTargets,
        total_images: images.length,
        total_interactive: interactive.length,
    };
}"""


class ResponsiveChecker(BaseChecker):
    """Checks responsive layout at multiple viewports."""

    checker_type = CheckerType.RESPONSIVE

    async def run(self) -> AuditResult:
        results: list[dict] = []
        issues_count = 0

        for name, (w, h) in self.settings.viewports.items():
            check = await self._check_viewport(name, (w, h))
            results.append(check)
            if check.get("has_horizontal_overflow"):
                issues_count += 1
            if check.get("oversized_images"):
                issues_count += len(check["oversized_images"])
            if name == "mobile" and not check.get("mobile_menu_found"):
                issues_count += 1

        return self._build_result(
            raw_data={"viewport_checks": results},
            summary=f"Checked {len(results)} viewports, found {issues_count} responsive issues",
        )

    async def _check_viewport(self, name: str, viewport: tuple[int, int]) -> dict:
        page = await self.browser.new_page(self.settings.migrated_url, viewport)
        await page.wait_for_timeout(1500)
        data = await page.evaluate(RESPONSIVE_CHECK_JS)
        data["viewport_name"] = name
        data["viewport_config"] = f"{viewport[0]}x{viewport[1]}"
        await page.context.close()
        return data

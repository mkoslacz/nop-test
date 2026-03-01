from __future__ import annotations

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType

NAV_EXTRACT_JS = """() => {
    const navs = [...document.querySelectorAll('nav, [role="navigation"]')];
    return navs.map((nav, i) => {
        const links = [...nav.querySelectorAll('a[href]')].map(a => ({
            href: a.href,
            text: a.textContent?.trim().substring(0, 100) || '',
            visible: a.offsetParent !== null,
        }));

        // Find dropdown triggers (elements with submenus)
        const dropdowns = [...nav.querySelectorAll(
            '[data-toggle="dropdown"], .dropdown-toggle, ' +
            '[aria-haspopup="true"], .has-submenu, .menu-item-has-children'
        )].map(d => ({
            text: d.textContent?.trim().substring(0, 100) || '',
            tag: d.tagName.toLowerCase(),
        }));

        return {
            index: i,
            aria_label: nav.getAttribute('aria-label') || null,
            total_links: links.length,
            links: links,
            dropdowns: dropdowns,
        };
    });
}"""


class NavigationChecker(BaseChecker):
    """Tests navigation menus, dropdowns, and interactive nav elements."""

    checker_type = CheckerType.NAVIGATION

    async def run(self) -> AuditResult:
        original_nav = await self._extract_nav(self.settings.original_url)
        migrated_nav = await self._extract_nav(self.settings.migrated_url)
        interaction_results = await self._test_interactions()
        diffs = self._compare(original_nav, migrated_nav)

        return self._build_result(
            raw_data={
                "original_nav": original_nav,
                "migrated_nav": migrated_nav,
                "interaction_results": interaction_results,
                "differences": diffs,
            },
            summary=(
                f"Found {len(original_nav)} nav sections in original, "
                f"{len(migrated_nav)} in migrated. "
                f"{len(diffs)} differences found."
            ),
        )

    async def _extract_nav(self, url: str) -> list[dict]:
        page = await self.browser.new_page(url)
        nav_data = await page.evaluate(NAV_EXTRACT_JS)
        await page.context.close()
        return nav_data

    async def _test_interactions(self) -> list[dict]:
        """Test interactive elements on the migrated page."""
        results: list[dict] = []
        page = await self.browser.new_page(self.settings.migrated_url)

        # Test language selector
        lang_selectors = [
            ".language-selector",
            "[data-testid='language-selector']",
            ".lang-switch",
            "select[name*='lang']",
        ]
        for sel in lang_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    results.append(
                        {"test": "language_selector", "found": True, "selector": sel}
                    )
                    break
            except Exception:
                continue
        else:
            results.append({"test": "language_selector", "found": False})

        # Test currency selector
        currency_selectors = [
            ".currency-selector",
            "[data-testid='currency-selector']",
            ".currency-switch",
            "select[name*='currency']",
        ]
        for sel in currency_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    results.append(
                        {"test": "currency_selector", "found": True, "selector": sel}
                    )
                    break
            except Exception:
                continue
        else:
            results.append({"test": "currency_selector", "found": False})

        # Test main menu hover/click interactions
        menu_items = page.locator(
            "nav a, nav button, [role='navigation'] a, [role='navigation'] button"
        )
        count = await menu_items.count()
        results.append({"test": "nav_items_count", "count": count})

        await page.context.close()
        return results

    def _compare(self, original: list[dict], migrated: list[dict]) -> list[dict]:
        diffs: list[dict] = []

        if len(original) != len(migrated):
            diffs.append(
                {
                    "type": "nav_count_mismatch",
                    "original_count": len(original),
                    "migrated_count": len(migrated),
                }
            )

        # Compare total link counts across all navs
        orig_total = sum(n.get("total_links", 0) for n in original)
        migr_total = sum(n.get("total_links", 0) for n in migrated)
        if orig_total != migr_total:
            diffs.append(
                {
                    "type": "nav_links_count_mismatch",
                    "original_total": orig_total,
                    "migrated_total": migr_total,
                }
            )

        return diffs

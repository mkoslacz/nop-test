from __future__ import annotations

from urllib.parse import urlparse

import httpx

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType


class LinkChecker(BaseChecker):
    """Extracts all links and checks for broken, misconfigured, or missing links."""

    checker_type = CheckerType.LINKS

    async def run(self) -> AuditResult:
        original_links = await self._extract_links(self.settings.original_url)
        migrated_links = await self._extract_links(self.settings.migrated_url)

        broken_links: list[dict] = []
        misconfigured_links: list[dict] = []

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0, verify=False
        ) as client:
            for link in migrated_links:
                href = link["href"]
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue

                # Check if misconfigured (pointing to nop-go subpages)
                if self._is_misconfigured(href):
                    misconfigured_links.append(link)

                # Check if broken
                try:
                    resp = await client.head(href, follow_redirects=True)
                    link["status_code"] = resp.status_code
                    if resp.status_code >= 400:
                        link["is_broken"] = True
                        broken_links.append(link)
                except Exception as e:
                    link["status_code"] = None
                    link["error"] = str(e)
                    link["is_broken"] = True
                    broken_links.append(link)

        # Compare link paths
        original_paths = {self._normalize_path(l["href"]) for l in original_links if l["href"]}
        migrated_paths = {self._normalize_path(l["href"]) for l in migrated_links if l["href"]}
        missing_paths = original_paths - migrated_paths
        extra_paths = migrated_paths - original_paths

        return self._build_result(
            raw_data={
                "total_links_original": len(original_links),
                "total_links_migrated": len(migrated_links),
                "broken_links": broken_links,
                "misconfigured_links": misconfigured_links,
                "missing_link_paths": sorted(missing_paths),
                "extra_link_paths": sorted(extra_paths),
                "all_migrated_links": migrated_links,
                "all_original_links": original_links,
            },
            summary=(
                f"Found {len(broken_links)} broken, "
                f"{len(misconfigured_links)} misconfigured, "
                f"{len(missing_paths)} missing, "
                f"{len(extra_paths)} extra links"
            ),
        )

    async def _extract_links(self, url: str) -> list[dict]:
        page = await self.browser.new_page(url)
        links = await page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')].map((a, i) => ({
                href: a.href,
                text: a.textContent?.trim().substring(0, 100) || '',
                location: a.closest('nav,header,footer,main,section')?.tagName?.toLowerCase() || 'body',
                index: i,
            }));
        }""")
        await page.context.close()
        return links

    def _is_misconfigured(self, href: str) -> bool:
        """A link on the migrated page pointing to nop-go.noclegi.pl subpages
        is misconfigured -- non-migrated pages should link to noclegi.pl."""
        parsed = urlparse(href)
        if parsed.netloc in self.settings.migrated_domains:
            path = parsed.path.rstrip("/")
            if path and path != "":
                return True
        return False

    def _normalize_path(self, href: str) -> str:
        parsed = urlparse(href)
        path = parsed.path.rstrip("/") or "/"
        # Normalize known domains to just paths for comparison
        if parsed.netloc in (
            self.settings.original_domain,
            *self.settings.migrated_domains,
        ):
            return path
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return f"{parsed.netloc}{path}"
        return path

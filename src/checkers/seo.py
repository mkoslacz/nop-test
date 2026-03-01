from __future__ import annotations

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType

SEO_EXTRACT_JS = """() => {
    const getMeta = (name) =>
        document.querySelector(`meta[name="${name}"]`)?.content || null;
    const getOG = (prop) =>
        document.querySelector(`meta[property="${prop}"]`)?.content || null;
    const schemas = [...document.querySelectorAll('script[type="application/ld+json"]')]
        .map(s => { try { return JSON.parse(s.textContent); } catch { return null; } })
        .filter(Boolean);
    return {
        title: document.title || null,
        description: getMeta('description'),
        canonical: document.querySelector('link[rel="canonical"]')?.href || null,
        robots: getMeta('robots'),
        og: {
            title: getOG('og:title'),
            description: getOG('og:description'),
            image: getOG('og:image'),
            url: getOG('og:url'),
            type: getOG('og:type'),
            site_name: getOG('og:site_name'),
        },
        twitter: {
            card: getMeta('twitter:card'),
            title: getMeta('twitter:title'),
            description: getMeta('twitter:description'),
            image: getMeta('twitter:image'),
        },
        schemas: schemas,
        headings: {
            h1: [...document.querySelectorAll('h1')].map(h => h.textContent.trim()),
            h2: [...document.querySelectorAll('h2')].map(h => h.textContent.trim()),
            h3: [...document.querySelectorAll('h3')].map(h => h.textContent.trim()),
        },
        hreflang: [...document.querySelectorAll('link[hreflang]')]
            .map(l => ({ lang: l.hreflang, href: l.href })),
        lang: document.documentElement.lang || null,
    };
}"""


class SEOChecker(BaseChecker):
    """Compares SEO elements between original and migrated pages."""

    checker_type = CheckerType.SEO

    async def run(self) -> AuditResult:
        original_seo = await self._extract_seo(self.settings.original_url)
        migrated_seo = await self._extract_seo(self.settings.migrated_url)
        diffs = self._compare(original_seo, migrated_seo)

        return self._build_result(
            raw_data={
                "original": original_seo,
                "migrated": migrated_seo,
                "differences": diffs,
            },
            summary=f"Found {len(diffs)} SEO differences between original and migrated",
        )

    async def _extract_seo(self, url: str) -> dict:
        page = await self.browser.new_page(url)
        seo_data = await page.evaluate(SEO_EXTRACT_JS)
        await page.context.close()
        return seo_data

    def _compare(self, original: dict, migrated: dict, prefix: str = "") -> list[dict]:
        diffs: list[dict] = []
        all_keys = set(list(original.keys()) + list(migrated.keys()))

        for key in sorted(all_keys):
            path = f"{prefix}.{key}" if prefix else key
            orig_val = original.get(key)
            migr_val = migrated.get(key)

            if isinstance(orig_val, dict) and isinstance(migr_val, dict):
                diffs.extend(self._compare(orig_val, migr_val, path))
            elif isinstance(orig_val, list) and isinstance(migr_val, list):
                if orig_val != migr_val:
                    diffs.append(
                        {
                            "field": path,
                            "original": orig_val,
                            "migrated": migr_val,
                            "type": "list_mismatch",
                        }
                    )
            elif orig_val != migr_val:
                diff_type = "missing_in_migrated" if migr_val is None else "changed"
                if orig_val is None:
                    diff_type = "new_in_migrated"
                diffs.append(
                    {
                        "field": path,
                        "original": orig_val,
                        "migrated": migr_val,
                        "type": diff_type,
                    }
                )
        return diffs

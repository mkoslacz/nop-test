from __future__ import annotations

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType

CONTENT_EXTRACT_JS = """() => {
    const sections = {};
    const selectors = {
        header: 'header',
        nav: 'nav',
        main: 'main, [role="main"], .main-content, #main',
        footer: 'footer',
        search_form: 'form[action*="search"], .search-form, .search-box, [data-testid*="search"]',
    };

    for (const [name, sel] of Object.entries(selectors)) {
        const el = document.querySelector(sel);
        if (el) {
            sections[name] = {
                text: el.innerText?.trim().substring(0, 5000) || '',
                html_length: el.innerHTML?.length || 0,
                child_count: el.children?.length || 0,
            };
        } else {
            sections[name] = null;
        }
    }

    // Extract all visible text blocks
    const body_text = document.body.innerText?.trim().substring(0, 10000) || '';

    // Count key interactive elements
    const counts = {
        images: document.querySelectorAll('img').length,
        buttons: document.querySelectorAll('button').length,
        inputs: document.querySelectorAll('input').length,
        selects: document.querySelectorAll('select').length,
        forms: document.querySelectorAll('form').length,
        links: document.querySelectorAll('a[href]').length,
        iframes: document.querySelectorAll('iframe').length,
    };

    return { sections, body_text, element_counts: counts };
}"""


class ContentChecker(BaseChecker):
    """Compares text content and page structure between original and migrated."""

    checker_type = CheckerType.CONTENT

    async def run(self) -> AuditResult:
        original = await self._extract_content(self.settings.original_url)
        migrated = await self._extract_content(self.settings.migrated_url)
        diffs = self._compare(original, migrated)

        return self._build_result(
            raw_data={
                "original": original,
                "migrated": migrated,
                "differences": diffs,
            },
            summary=f"Found {len(diffs)} content differences",
        )

    async def _extract_content(self, url: str) -> dict:
        page = await self.browser.new_page(url)
        data = await page.evaluate(CONTENT_EXTRACT_JS)
        await page.context.close()
        return data

    def _compare(self, original: dict, migrated: dict) -> list[dict]:
        diffs: list[dict] = []

        # Compare section presence
        for section_name in set(
            list((original.get("sections") or {}).keys())
            + list((migrated.get("sections") or {}).keys())
        ):
            orig_section = (original.get("sections") or {}).get(section_name)
            migr_section = (migrated.get("sections") or {}).get(section_name)

            if orig_section and not migr_section:
                diffs.append(
                    {
                        "type": "missing_section",
                        "section": section_name,
                        "detail": "Section exists in original but missing in migrated",
                    }
                )
            elif not orig_section and migr_section:
                diffs.append(
                    {
                        "type": "extra_section",
                        "section": section_name,
                        "detail": "Section exists in migrated but not in original",
                    }
                )
            elif orig_section and migr_section:
                # Compare text length difference
                orig_len = len(orig_section.get("text", ""))
                migr_len = len(migr_section.get("text", ""))
                if abs(orig_len - migr_len) > max(orig_len * 0.2, 50):
                    diffs.append(
                        {
                            "type": "content_length_mismatch",
                            "section": section_name,
                            "original_length": orig_len,
                            "migrated_length": migr_len,
                            "original_text_preview": orig_section["text"][:200],
                            "migrated_text_preview": migr_section["text"][:200],
                        }
                    )

        # Compare element counts
        orig_counts = original.get("element_counts", {})
        migr_counts = migrated.get("element_counts", {})
        for element_type in set(list(orig_counts.keys()) + list(migr_counts.keys())):
            orig_count = orig_counts.get(element_type, 0)
            migr_count = migr_counts.get(element_type, 0)
            if orig_count != migr_count:
                diffs.append(
                    {
                        "type": "element_count_mismatch",
                        "element": element_type,
                        "original_count": orig_count,
                        "migrated_count": migr_count,
                    }
                )

        return diffs

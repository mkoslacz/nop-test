from __future__ import annotations

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType

# Extract a rich structural snapshot of the page for LLM open-ended analysis.
# This intentionally captures MORE than the other checkers — raw HTML fragments,
# computed styles of key elements, accessibility tree, cookie banners, third-party
# scripts, etc. The goal is to let the LLM spot things no checker was coded for.
PAGE_SNAPSHOT_JS = """() => {
    // 1. Accessibility / ARIA snapshot
    const ariaSnapshot = (() => {
        const walk = (el, depth) => {
            if (depth > 6 || !el) return '';
            const tag = el.tagName?.toLowerCase() || '';
            const role = el.getAttribute?.('role') || '';
            const ariaLabel = el.getAttribute?.('aria-label') || '';
            const ariaHidden = el.getAttribute?.('aria-hidden');
            const id = el.id ? `#${el.id}` : '';
            const cls = el.className && typeof el.className === 'string'
                ? '.' + el.className.trim().split(/\\s+/).slice(0, 3).join('.')
                : '';

            let line = '  '.repeat(depth) + tag + id + cls;
            if (role) line += ` [role=${role}]`;
            if (ariaLabel) line += ` [aria-label="${ariaLabel.substring(0, 60)}"]`;
            if (ariaHidden === 'true') line += ' [aria-hidden]';

            // For text-bearing leaf elements, include short text
            if (el.children.length === 0 && el.textContent?.trim()) {
                const txt = el.textContent.trim().substring(0, 80);
                line += ` "${txt}"`;
            }

            let result = line + '\\n';
            for (const child of el.children) {
                result += walk(child, depth + 1);
            }
            return result;
        };
        return walk(document.body, 0).substring(0, 15000);
    })();

    // 2. <head> content (critical for SEO, favicons, preloads, etc.)
    const headHTML = document.head.innerHTML.substring(0, 8000);

    // 3. Key structural HTML fragments (first 3000 chars of each major section)
    const fragments = {};
    const sectionSelectors = {
        header: 'header',
        hero_search: '.search-form, .search-box, [class*="hero"], [class*="search-section"], form',
        main_content: 'main, [role="main"]',
        footer: 'footer',
    };
    for (const [name, sel] of Object.entries(sectionSelectors)) {
        const el = document.querySelector(sel);
        if (el) {
            fragments[name] = {
                outerHTML: el.outerHTML.substring(0, 3000),
                computed_styles: (() => {
                    const s = window.getComputedStyle(el);
                    return {
                        background: s.backgroundColor,
                        color: s.color,
                        font: s.font,
                        padding: s.padding,
                        margin: s.margin,
                        display: s.display,
                        position: s.position,
                    };
                })(),
            };
        }
    }

    // 4. All <script> tags — src and type (to detect missing/extra third-party scripts)
    const scripts = [...document.querySelectorAll('script')].map(s => ({
        src: s.src?.substring(0, 200) || null,
        type: s.type || 'text/javascript',
        inline_length: s.src ? 0 : (s.textContent?.length || 0),
    }));

    // 5. All <link> tags in <head> (stylesheets, preloads, icons, etc.)
    const headLinks = [...document.querySelectorAll('head link')].map(l => ({
        rel: l.rel,
        href: l.href?.substring(0, 200) || null,
        type: l.type || null,
        sizes: l.sizes?.value || null,
    }));

    // 6. Cookie/consent banners detection
    const cookieBanners = [...document.querySelectorAll(
        '[class*="cookie"], [class*="consent"], [class*="gdpr"], ' +
        '[id*="cookie"], [id*="consent"], [id*="gdpr"]'
    )].map(el => ({
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        class: el.className?.substring?.(0, 100) || null,
        visible: el.offsetParent !== null,
        text_preview: el.textContent?.trim().substring(0, 200) || '',
    }));

    // 7. Images — all img tags with src, alt, loading, dimensions
    const images = [...document.querySelectorAll('img')].slice(0, 50).map(img => ({
        src: img.src?.substring(0, 200) || null,
        alt: img.alt?.substring(0, 100) || null,
        loading: img.loading || null,
        width: img.naturalWidth,
        height: img.naturalHeight,
        display_width: img.offsetWidth,
        display_height: img.offsetHeight,
    }));

    // 8. Inline styles and CSS custom properties on :root
    const rootStyles = (() => {
        try {
            const s = window.getComputedStyle(document.documentElement);
            const vars = {};
            for (let i = 0; i < s.length; i++) {
                const prop = s[i];
                if (prop.startsWith('--')) {
                    vars[prop] = s.getPropertyValue(prop).trim();
                }
            }
            return vars;
        } catch { return {}; }
    })();

    return {
        url: window.location.href,
        title: document.title,
        lang: document.documentElement.lang,
        doctype: document.doctype ? document.doctype.name : null,
        aria_tree: ariaSnapshot,
        head_html: headHTML,
        section_fragments: fragments,
        scripts: scripts,
        head_links: headLinks,
        cookie_banners: cookieBanners,
        images: images,
        css_custom_properties: rootStyles,
    };
}"""


class LLMReviewChecker(BaseChecker):
    """Extracts raw page structure for open-ended LLM analysis beyond coded checkers."""

    checker_type = CheckerType.LLM_REVIEW

    async def run(self) -> AuditResult:
        original = await self._extract_snapshot(self.settings.original_url)
        migrated = await self._extract_snapshot(self.settings.migrated_url)

        return self._build_result(
            raw_data={
                "original_snapshot": original,
                "migrated_snapshot": migrated,
            },
            summary="Captured raw page snapshots for open-ended LLM review",
        )

    async def _extract_snapshot(self, url: str) -> dict:
        page = await self.browser.new_page(url)
        await page.wait_for_timeout(2000)
        data = await page.evaluate(PAGE_SNAPSHOT_JS)
        await page.context.close()
        return data

from __future__ import annotations

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType

PERF_EXTRACT_JS = """() => {
    const timing = performance.timing;
    const nav = timing.navigationStart;

    // Resource breakdown
    const resources = performance.getEntriesByType('resource');
    const breakdown = {};
    let totalSize = 0;
    for (const r of resources) {
        const type = r.initiatorType || 'other';
        breakdown[type] = (breakdown[type] || 0) + 1;
        totalSize += r.transferSize || 0;
    }

    // Core Web Vitals approximation
    let lcp = null;
    try {
        const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
        if (lcpEntries.length > 0) {
            lcp = lcpEntries[lcpEntries.length - 1].startTime;
        }
    } catch {}

    let cls = null;
    try {
        const clsEntries = performance.getEntriesByType('layout-shift');
        if (clsEntries.length > 0) {
            cls = clsEntries.reduce((sum, e) => sum + (e.hadRecentInput ? 0 : e.value), 0);
        }
    } catch {}

    return {
        dom_content_loaded_ms: timing.domContentLoadedEventEnd - nav,
        load_time_ms: timing.loadEventEnd - nav,
        ttfb_ms: timing.responseStart - nav,
        dom_interactive_ms: timing.domInteractive - nav,
        total_resources: resources.length,
        total_transfer_size_bytes: totalSize,
        resource_breakdown: breakdown,
        lcp_ms: lcp,
        cls: cls,
        dom_elements: document.getElementsByTagName('*').length,
    };
}"""


class PerformanceChecker(BaseChecker):
    """Compares page load performance between original and migrated."""

    checker_type = CheckerType.PERFORMANCE

    async def run(self) -> AuditResult:
        original_perf = await self._measure(self.settings.original_url)
        migrated_perf = await self._measure(self.settings.migrated_url)
        comparison = self._compare(original_perf, migrated_perf)

        return self._build_result(
            raw_data={
                "original": original_perf,
                "migrated": migrated_perf,
                "comparison": comparison,
            },
            summary=self._summarize(comparison),
        )

    async def _measure(self, url: str) -> dict:
        page = await self.browser.new_page(url)
        await page.wait_for_timeout(2000)  # let everything settle
        data = await page.evaluate(PERF_EXTRACT_JS)
        data["url"] = url
        await page.context.close()
        return data

    def _compare(self, original: dict, migrated: dict) -> list[dict]:
        comparisons: list[dict] = []
        metrics = [
            ("dom_content_loaded_ms", "DOM Content Loaded", "ms"),
            ("load_time_ms", "Full Load Time", "ms"),
            ("ttfb_ms", "Time to First Byte", "ms"),
            ("total_resources", "Total Resources", "count"),
            ("total_transfer_size_bytes", "Total Transfer Size", "bytes"),
            ("dom_elements", "DOM Elements", "count"),
            ("lcp_ms", "Largest Contentful Paint", "ms"),
        ]

        for key, label, unit in metrics:
            orig_val = original.get(key)
            migr_val = migrated.get(key)
            if orig_val is None or migr_val is None:
                continue

            diff = migr_val - orig_val
            if orig_val > 0:
                pct_change = (diff / orig_val) * 100
            else:
                pct_change = 0.0

            # Flag regressions > 20%
            is_regression = pct_change > 20 and unit == "ms"

            comparisons.append(
                {
                    "metric": label,
                    "key": key,
                    "unit": unit,
                    "original": orig_val,
                    "migrated": migr_val,
                    "difference": diff,
                    "percent_change": round(pct_change, 1),
                    "is_regression": is_regression,
                }
            )

        return comparisons

    def _summarize(self, comparisons: list[dict]) -> str:
        regressions = [c for c in comparisons if c.get("is_regression")]
        if regressions:
            names = ", ".join(c["metric"] for c in regressions)
            return f"Performance regressions detected in: {names}"
        return "No significant performance regressions detected"

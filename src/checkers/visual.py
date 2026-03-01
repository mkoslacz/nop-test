from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType


class VisualChecker(BaseChecker):
    """Captures full-page screenshots at multiple viewports and computes pixel diffs."""

    checker_type = CheckerType.VISUAL

    async def run(self) -> AuditResult:
        screenshots_dir = self.settings.output_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        pairs: list[dict] = []
        for name, (w, h) in self.settings.viewports.items():
            orig_path = await self._capture(
                self.settings.original_url, name, "original", (w, h), screenshots_dir
            )
            migr_path = await self._capture(
                self.settings.migrated_url, name, "migrated", (w, h), screenshots_dir
            )
            diff_pct, diff_path = self._compute_diff(orig_path, migr_path, screenshots_dir, name)
            pairs.append(
                {
                    "viewport": name,
                    "viewport_size": f"{w}x{h}",
                    "original_path": str(orig_path),
                    "migrated_path": str(migr_path),
                    "diff_path": str(diff_path) if diff_path else None,
                    "diff_percentage": diff_pct,
                }
            )

        max_diff = max((p["diff_percentage"] for p in pairs), default=0.0)
        return self._build_result(
            raw_data={"screenshot_pairs": pairs},
            summary=f"Captured {len(pairs)} viewport comparisons. Max pixel diff: {max_diff:.1f}%",
        )

    async def _capture(
        self,
        url: str,
        viewport_name: str,
        label: str,
        viewport: tuple[int, int],
        out_dir: Path,
    ) -> Path:
        page = await self.browser.new_page(url, viewport)
        await self._dismiss_cookies(page)
        await page.wait_for_timeout(2000)
        path = out_dir / f"{label}_{viewport_name}.png"
        await page.screenshot(full_page=True, path=str(path))
        await page.context.close()
        return path

    async def _dismiss_cookies(self, page) -> None:
        """Try to dismiss cookie banners with common selectors."""
        selectors = [
            "[data-testid='cookie-accept']",
            ".cookie-consent-accept",
            "#cookie-accept",
            "button:has-text('Akceptuję')",
            "button:has-text('Akceptuj')",
            "button:has-text('Accept')",
            "button:has-text('Zgadzam')",
            ".cc-btn.cc-dismiss",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    def _compute_diff(
        self, path_a: Path, path_b: Path, out_dir: Path, viewport_name: str
    ) -> tuple[float, Path | None]:
        try:
            img_a = Image.open(path_a).convert("RGB")
            img_b = Image.open(path_b).convert("RGB")

            # Resize to common dimensions (use the larger canvas)
            max_w = max(img_a.width, img_b.width)
            max_h = max(img_a.height, img_b.height)

            canvas_a = Image.new("RGB", (max_w, max_h), (255, 255, 255))
            canvas_a.paste(img_a, (0, 0))
            canvas_b = Image.new("RGB", (max_w, max_h), (255, 255, 255))
            canvas_b.paste(img_b, (0, 0))

            diff = ImageChops.difference(canvas_a, canvas_b)
            # Count non-zero pixels
            pixels = list(diff.getdata())
            total = len(pixels)
            different = sum(1 for p in pixels if p != (0, 0, 0))
            pct = (different / total * 100) if total > 0 else 0.0

            diff_path = out_dir / f"diff_{viewport_name}.png"
            # Enhance diff visibility
            enhanced = diff.point(lambda x: min(x * 5, 255))
            enhanced.save(str(diff_path))
            return pct, diff_path
        except Exception:
            return 0.0, None

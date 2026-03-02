from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.llm.client import LLMClient
from src.llm.prompts import (
    SYSTEM_PROMPT,
    build_llm_review_prompt,
    build_synthesis_prompt,
    build_visual_prompt,
)
from src.models.findings import AuditResult


class Synthesizer:
    """Three-stage LLM pipeline:
    1. Visual analysis — per screenshot pair
    2. Open-ended LLM review — raw page snapshots for Claude to freely analyze
    3. Final synthesis — all compacted data combined into structured bug report
    """

    def __init__(self, llm_client: LLMClient, log: Callable[[str], None] | None = None):
        self.llm = llm_client
        self._log = log or (lambda _: None)

    def synthesize(
        self, results: list[AuditResult], screenshot_pairs: list[dict]
    ) -> str:
        """Run full 3-stage synthesis and return markdown report string."""
        visual_analyses = self._stage_visual(screenshot_pairs)
        llm_review_analysis = self._stage_llm_review(results)
        return self._stage_final_synthesis(
            results, visual_analyses, llm_review_analysis
        )

    # ── Stage 1: Visual ─────────────────────────────────────────────

    def _stage_visual(self, screenshot_pairs: list[dict]) -> list[dict]:
        """Send screenshot pairs to Claude Vision for qualitative comparison."""
        visual_analyses: list[dict] = []
        for pair in screenshot_pairs:
            orig_path = Path(pair["original_path"])
            migr_path = Path(pair["migrated_path"])
            diff_path = Path(pair["diff_path"]) if pair.get("diff_path") else None

            if orig_path.exists() and migr_path.exists():
                prompt = build_visual_prompt(
                    viewport=pair["viewport"],
                    viewport_size=pair.get("viewport_size", "unknown"),
                )
                try:
                    self._log(f"  [Stage 1/3] Analyzing {pair['viewport']} screenshots...")
                    analysis = self.llm.compare_screenshots(
                        original_path=orig_path,
                        migrated_path=migr_path,
                        diff_path=diff_path,
                        viewport=pair["viewport"],
                        prompt=prompt,
                    )
                except Exception as e:
                    analysis = f"Visual analysis failed: {e}"

                visual_analyses.append(
                    {
                        "viewport": pair["viewport"],
                        "viewport_size": pair.get("viewport_size"),
                        "pixel_diff_percentage": pair.get("diff_percentage"),
                        "analysis": analysis,
                    }
                )
        return visual_analyses

    # ── Stage 2: Open-ended LLM review ──────────────────────────────

    def _stage_llm_review(self, results: list[AuditResult]) -> str | None:
        """Send raw page snapshots for open-ended Claude analysis."""
        llm_review_result = None
        for r in results:
            if r.checker_type.value == "llm_review":
                llm_review_result = r
                break

        if not llm_review_result:
            return None

        original_snapshot = llm_review_result.raw_data.get("original_snapshot", {})
        migrated_snapshot = llm_review_result.raw_data.get("migrated_snapshot", {})

        orig_json = json.dumps(original_snapshot, indent=2, default=str, ensure_ascii=False)
        migr_json = json.dumps(migrated_snapshot, indent=2, default=str, ensure_ascii=False)

        if len(orig_json) > 40_000:
            orig_json = self._truncate_snapshot(original_snapshot)
        if len(migr_json) > 40_000:
            migr_json = self._truncate_snapshot(migrated_snapshot)

        prompt = build_llm_review_prompt(orig_json, migr_json)

        try:
            self._log("  [Stage 2/3] Running open-ended LLM review of page structure...")
            return self.llm.analyze_text(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                max_tokens=4096,
            )
        except Exception as e:
            self._log(f"  [yellow]LLM review failed: {e}[/yellow]")
            return f"LLM review failed: {e}"

    # ── Stage 3: Final synthesis ────────────────────────────────────

    def _stage_final_synthesis(
        self,
        results: list[AuditResult],
        visual_analyses: list[dict],
        llm_review_analysis: str | None,
    ) -> str:
        """Compact all checker data, combine with LLM outputs, and synthesize."""
        compacted_results = []
        for r in results:
            if r.checker_type.value in ("visual", "llm_review"):
                continue
            compacted = self._compact_checker_data(r.checker_type.value, r.raw_data)
            compacted_results.append(
                {
                    "type": r.checker_type.value,
                    "summary": r.summary,
                    "data": compacted,
                }
            )

        all_data: dict = {
            "visual_analyses": visual_analyses,
            "checker_results": compacted_results,
        }
        if llm_review_analysis:
            all_data["llm_open_review"] = llm_review_analysis

        raw_json = json.dumps(all_data, indent=2, default=str, ensure_ascii=False)
        self._log(f"  Stage 3 payload: {len(raw_json):,} chars (~{len(raw_json)//4:,} tokens)")

        self._log("  [Stage 3/3] Generating final report...")
        return self.llm.analyze_text(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_synthesis_prompt(raw_json),
            max_tokens=8192,
        )

    # ── Per-checker data compaction ─────────────────────────────────

    def _compact_checker_data(self, checker_type: str, raw_data: dict) -> dict:
        """Intelligently compact raw checker data for stage 3.

        Each checker type gets dedicated logic to keep the signal
        (broken links, diffs, failures) and drop the noise
        (full link lists, raw HTML text, repetitive entries).
        """
        compactor = {
            "links": self._compact_links,
            "seo": self._compact_seo,
            "content": self._compact_content,
            "navigation": self._compact_passthrough,
            "forms": self._compact_passthrough,
            "responsive": self._compact_passthrough,
            "performance": self._compact_performance,
        }
        fn = compactor.get(checker_type, self._compact_passthrough)
        return fn(raw_data)

    def _compact_links(self, data: dict) -> dict:
        """Links checker: keep broken + misconfigured with examples, drop full lists."""
        broken = data.get("broken_links", [])
        misconfigured = data.get("misconfigured_links", [])
        missing = data.get("missing_link_paths", [])
        extra = data.get("extra_link_paths", [])

        # Group misconfigured links by path pattern
        misconfig_paths = {}
        for link in misconfigured:
            from urllib.parse import urlparse
            path = urlparse(link.get("href", "")).path
            section = link.get("location", "unknown")
            key = f"{section}:{path}"
            if key not in misconfig_paths:
                misconfig_paths[key] = {"href": link.get("href"), "text": link.get("text", ""), "section": section}

        # Deduplicate — keep unique paths only
        unique_misconfigured = list(misconfig_paths.values())

        return {
            "total_links_original": data.get("total_links_original", 0),
            "total_links_migrated": data.get("total_links_migrated", 0),
            "broken_links": broken,  # usually few — keep all
            "broken_count": len(broken),
            "misconfigured_links_sample": unique_misconfigured[:30],
            "misconfigured_count": len(misconfigured),
            "misconfigured_unique_paths": len(unique_misconfigured),
            "missing_link_paths": missing[:20],
            "missing_count": len(missing),
            "extra_link_paths": extra[:20],
            "extra_count": len(extra),
        }

    def _compact_seo(self, data: dict) -> dict:
        """SEO checker: keep only the differences, drop matching raw data."""
        diffs = data.get("differences", [])
        # Include original/migrated only for fields that differ
        return {
            "differences": diffs,
            "diff_count": len(diffs),
            # Keep schema comparison but truncate large JSON-LD
            "original_schemas_count": len((data.get("original") or {}).get("schemas", [])),
            "migrated_schemas_count": len((data.get("migrated") or {}).get("schemas", [])),
        }

    def _compact_content(self, data: dict) -> dict:
        """Content checker: keep diffs and counts, drop raw body_text."""
        result = {
            "differences": data.get("differences", []),
        }
        # Drop raw body_text and full section text — just keep structure
        for side in ("original", "migrated"):
            side_data = data.get(side, {})
            if side_data:
                result[f"{side}_element_counts"] = side_data.get("element_counts", {})
                # Keep only section presence/length, not full text
                sections = side_data.get("sections", {})
                result[f"{side}_sections"] = {
                    name: {
                        "present": sec is not None,
                        "text_length": len(sec.get("text", "")) if sec else 0,
                    }
                    for name, sec in (sections or {}).items()
                }
        return result

    def _compact_performance(self, data: dict) -> dict:
        """Performance checker: keep comparison table, drop raw timing objects."""
        return {
            "comparison": data.get("comparison", []),
        }

    def _compact_passthrough(self, data: dict) -> dict:
        """Small checkers (navigation, forms, responsive): pass through as-is."""
        return data

    # ── Snapshot truncation (for stage 2) ───────────────────────────

    def _truncate_snapshot(self, snapshot: dict) -> str:
        """Truncate snapshot fields to fit within stage 2 context limits."""
        truncated = dict(snapshot)
        if "head_html" in truncated:
            truncated["head_html"] = truncated["head_html"][:4000]
        if "aria_tree" in truncated:
            truncated["aria_tree"] = truncated["aria_tree"][:8000]
        for name, frag in (truncated.get("section_fragments") or {}).items():
            if isinstance(frag, dict) and "outerHTML" in frag:
                frag["outerHTML"] = frag["outerHTML"][:2000]
        if "scripts" in truncated and len(truncated["scripts"]) > 30:
            truncated["scripts"] = truncated["scripts"][:30]
            truncated["scripts_note"] = "Truncated to first 30"
        if "images" in truncated and len(truncated["images"]) > 20:
            truncated["images"] = truncated["images"][:20]
            truncated["images_note"] = "Truncated to first 20"
        return json.dumps(truncated, indent=2, default=str, ensure_ascii=False)

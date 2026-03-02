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
    3. Final synthesis — all data combined into structured bug report
    """

    def __init__(self, llm_client: LLMClient, log: Callable[[str], None] | None = None):
        self.llm = llm_client
        self._log = log or (lambda _: None)

    def synthesize(
        self, results: list[AuditResult], screenshot_pairs: list[dict]
    ) -> str:
        """Run full 3-stage synthesis and return markdown report string."""

        # Stage 1: Visual analysis per screenshot pair
        visual_analyses = self._stage_visual(screenshot_pairs)

        # Stage 2: Open-ended LLM review of raw page snapshots
        llm_review_analysis = self._stage_llm_review(results)

        # Stage 3: Final synthesis — everything combined
        return self._stage_final_synthesis(
            results, visual_analyses, llm_review_analysis
        )

    def _stage_visual(self, screenshot_pairs: list[dict]) -> list[dict]:
        """Stage 1: Send screenshot pairs to Claude Vision."""
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

    def _stage_llm_review(self, results: list[AuditResult]) -> str | None:
        """Stage 2: Send raw page snapshots for open-ended Claude analysis."""
        llm_review_result = None
        for r in results:
            if r.checker_type.value == "llm_review":
                llm_review_result = r
                break

        if not llm_review_result:
            return None

        original_snapshot = llm_review_result.raw_data.get("original_snapshot", {})
        migrated_snapshot = llm_review_result.raw_data.get("migrated_snapshot", {})

        # Serialize snapshots — truncate large fields to fit in context
        orig_json = json.dumps(original_snapshot, indent=2, default=str, ensure_ascii=False)
        migr_json = json.dumps(migrated_snapshot, indent=2, default=str, ensure_ascii=False)

        # Cap each at ~40K chars to leave room for prompt + response
        if len(orig_json) > 40_000:
            orig_json = self._truncate_snapshot(original_snapshot)
        if len(migr_json) > 40_000:
            migr_json = self._truncate_snapshot(migrated_snapshot)

        prompt = build_llm_review_prompt(orig_json, migr_json)

        try:
            self._log("  [Stage 2/3] Running open-ended LLM review of page structure...")
            analysis = self.llm.analyze_text(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                max_tokens=4096,
            )
            return analysis
        except Exception as e:
            self._log(f"  [yellow]LLM review failed: {e}[/yellow]")
            return f"LLM review failed: {e}"

    def _stage_final_synthesis(
        self,
        results: list[AuditResult],
        visual_analyses: list[dict],
        llm_review_analysis: str | None,
    ) -> str:
        """Stage 3: Combine all data and generate final report."""
        all_raw_data: dict = {
            "visual_analyses": visual_analyses,
            "checker_results": [
                {
                    "type": r.checker_type.value,
                    "summary": r.summary,
                    "data": r.raw_data,
                }
                for r in results
                if r.checker_type.value not in ("visual", "llm_review")
            ],
        }

        if llm_review_analysis:
            all_raw_data["llm_open_review"] = llm_review_analysis

        raw_json = json.dumps(all_raw_data, indent=2, default=str, ensure_ascii=False)
        if len(raw_json) > 100_000:
            raw_json = self._truncate_large_data(all_raw_data)

        self._log("  [Stage 3/3] Generating final report...")
        return self.llm.analyze_text(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_synthesis_prompt(raw_json),
            max_tokens=8192,
        )

    def _truncate_snapshot(self, snapshot: dict) -> str:
        """Truncate snapshot fields to fit within context limits."""
        truncated = dict(snapshot)
        # Trim the largest fields
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

    def _truncate_large_data(self, data: dict) -> str:
        """Truncate large link lists while preserving important findings."""
        truncated = dict(data)

        for result in truncated.get("checker_results", []):
            result_data = result.get("data", {})
            for key in ("all_migrated_links", "all_original_links"):
                if key in result_data and len(result_data[key]) > 20:
                    total = len(result_data[key])
                    result_data[key] = result_data[key][:20]
                    result_data[f"{key}_note"] = (
                        f"Truncated to first 20 of {total} total. "
                        f"See broken_links and misconfigured_links for important findings."
                    )

        # If llm_open_review is very long, truncate it too
        if "llm_open_review" in truncated and len(truncated["llm_open_review"]) > 6000:
            truncated["llm_open_review"] = truncated["llm_open_review"][:6000] + "\n[truncated]"

        return json.dumps(truncated, indent=2, default=str, ensure_ascii=False)

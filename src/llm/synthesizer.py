from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.llm.client import LLMClient
from src.llm.prompts import SYSTEM_PROMPT, build_synthesis_prompt, build_visual_prompt
from src.models.findings import AuditResult


class Synthesizer:
    """Two-stage LLM pipeline: visual analysis per screenshot pair, then full synthesis."""

    def __init__(self, llm_client: LLMClient, log: Callable[[str], None] | None = None):
        self.llm = llm_client
        self._log = log or (lambda _: None)

    def synthesize(
        self, results: list[AuditResult], screenshot_pairs: list[dict]
    ) -> str:
        """Run full synthesis and return markdown report string."""
        # Stage 1: Visual analysis per screenshot pair
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
                    self._log(f"  Analyzing {pair['viewport']} screenshots...")
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

        # Stage 2: Full synthesis
        all_raw_data = {
            "visual_analyses": visual_analyses,
            "checker_results": [
                {
                    "type": r.checker_type.value,
                    "summary": r.summary,
                    "data": r.raw_data,
                }
                for r in results
                if r.checker_type.value != "visual"
            ],
        }

        raw_json = json.dumps(all_raw_data, indent=2, default=str, ensure_ascii=False)
        if len(raw_json) > 100_000:
            raw_json = self._truncate_large_data(all_raw_data)

        self._log("  Generating final report...")
        return self.llm.analyze_text(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_synthesis_prompt(raw_json),
            max_tokens=8192,
        )

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

        return json.dumps(truncated, indent=2, default=str, ensure_ascii=False)

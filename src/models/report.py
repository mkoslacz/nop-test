from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.findings import AuditResult, Severity


@dataclass
class Issue:
    id: str  # e.g., "LINK-001"
    title: str
    severity: Severity
    category: str
    description: str
    reproduction_steps: list[str]
    expected_behavior: str
    actual_behavior: str
    affected_viewport: str | None = None
    screenshot_paths: list[Path] = field(default_factory=list)
    related_urls: list[str] = field(default_factory=list)


@dataclass
class Report:
    title: str
    generated_at: str
    original_url: str
    migrated_url: str
    executive_summary: str
    issues: list[Issue]
    statistics: dict
    raw_audit_results: list[AuditResult] = field(default_factory=list)

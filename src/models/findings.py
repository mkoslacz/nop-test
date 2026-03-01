from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"
    INFO = "Info"


class CheckerType(str, Enum):
    VISUAL = "visual"
    LINKS = "links"
    SEO = "seo"
    CONTENT = "content"
    NAVIGATION = "navigation"
    FORMS = "forms"
    RESPONSIVE = "responsive"
    PERFORMANCE = "performance"


@dataclass
class Screenshot:
    path: Path
    url: str
    viewport: str
    label: str  # "original" or "migrated"
    full_page: bool = True


@dataclass
class ScreenshotPair:
    original: Screenshot
    migrated: Screenshot
    viewport: str
    pixel_diff_percentage: float | None = None
    diff_image_path: Path | None = None


@dataclass
class LinkInfo:
    href: str
    resolved_url: str
    text: str
    location: str
    status_code: int | None = None
    is_internal: bool = True
    points_to_original: bool = False
    is_broken: bool = False
    redirect_chain: list[str] = field(default_factory=list)


@dataclass
class MetaTag:
    name: str
    content: str
    source: str


@dataclass
class PerformanceMetrics:
    url: str
    load_time_ms: float
    dom_content_loaded_ms: float
    total_resources: int
    total_size_bytes: int
    resource_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class AuditResult:
    checker_type: CheckerType
    raw_data: dict
    summary: str
    timestamp: str

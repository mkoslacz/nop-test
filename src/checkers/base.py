from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from config.settings import Settings
from src.browser.context import BrowserManager
from src.models.findings import AuditResult, CheckerType


class BaseChecker(ABC):
    """Abstract base for all audit checkers."""

    checker_type: CheckerType

    def __init__(self, browser: BrowserManager, settings: Settings):
        self.browser = browser
        self.settings = settings

    @abstractmethod
    async def run(self) -> AuditResult:
        ...

    def _build_result(self, raw_data: dict, summary: str) -> AuditResult:
        return AuditResult(
            checker_type=self.checker_type,
            raw_data=raw_data,
            summary=summary,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from src.models.findings import AuditResult, CheckerType


class CacheManager:
    def __init__(self, cache_dir: Path, ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.ttl = timedelta(hours=ttl_hours)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, checker_type: str, params: dict) -> str:
        raw = json.dumps({"type": checker_type, **params}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, checker_type: str, params: dict) -> AuditResult | None:
        path = self.cache_dir / f"{self._key(checker_type, params)}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        cached_at = datetime.fromisoformat(data["timestamp"])
        if datetime.utcnow() - cached_at > self.ttl:
            path.unlink()
            return None
        return AuditResult(
            checker_type=CheckerType(data["checker_type"]),
            raw_data=data["raw_data"],
            summary=data["summary"],
            timestamp=data["timestamp"],
        )

    def put(self, result: AuditResult, params: dict) -> None:
        path = self.cache_dir / f"{self._key(result.checker_type.value, params)}.json"
        data = {
            "checker_type": result.checker_type.value,
            "raw_data": result.raw_data,
            "summary": result.summary,
            "timestamp": result.timestamp,
        }
        path.write_text(json.dumps(data, indent=2, default=str))

    def invalidate_all(self) -> None:
        for f in self.cache_dir.glob("*.json"):
            f.unlink()

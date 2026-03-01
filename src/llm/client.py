from __future__ import annotations

import base64
from pathlib import Path

import anthropic


class LLMClient:
    """Wraps Anthropic API for text and vision analysis.

    Authentication: Set ANTHROPIC_API_KEY env var with your Anthropic API key.
    Note: Claude Max/Pro OAuth tokens cannot be used in third-party apps per
    Anthropic's ToS — an API key with usage-based billing is required.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze_text(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 8192
    ) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text

    def compare_screenshots(
        self,
        original_path: Path,
        migrated_path: Path,
        diff_path: Path | None,
        viewport: str,
        prompt: str,
    ) -> str:
        content: list[dict] = []
        content.append({"type": "text", "text": f"Original homepage ({viewport} viewport):"})
        content.append(self._image_block(original_path))
        content.append({"type": "text", "text": f"Migrated homepage ({viewport} viewport):"})
        content.append(self._image_block(migrated_path))
        if diff_path and diff_path.exists():
            content.append({"type": "text", "text": "Pixel diff overlay (differences highlighted):"})
            content.append(self._image_block(diff_path))
        content.append({"type": "text", "text": prompt})

        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        return message.content[0].text

    def _image_block(self, path: Path) -> dict:
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        suffix = path.suffix.lower()
        media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        media_type = media_types.get(suffix, "image/png")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }

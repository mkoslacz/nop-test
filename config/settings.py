from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "NOP_", "env_file": ".env", "extra": "ignore"}

    original_url: str = "https://noclegi.pl"
    migrated_url: str = "https://nop-go.noclegi.pl"
    output_dir: Path = Path("./output")
    cache_enabled: bool = True
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    llm_model: str = "claude-sonnet-4-20250514"
    page_timeout: int = 30000
    action_timeout: int = 5000

    viewports: dict[str, tuple[int, int]] = {
        "mobile": (375, 812),
        "tablet": (768, 1024),
        "desktop": (1440, 900),
    }

    migrated_domains: list[str] = ["nop-go.noclegi.pl"]
    original_domain: str = "noclegi.pl"
    skip_external_links: bool = True
    llm_max_tokens: int = 8192

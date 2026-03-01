from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console

from config.settings import Settings
from src.runner import AuditRunner, CHECKER_REGISTRY


@click.group()
def main():
    """nop-test: Website migration audit tool for noclegi.pl → nop-go.noclegi.pl"""
    pass


@main.command()
@click.option(
    "--checkers", "-c",
    multiple=True,
    default=None,
    help="Specific checkers to run. Can be repeated. "
    f"Available: {', '.join(CHECKER_REGISTRY.keys())}",
)
@click.option("--no-cache", is_flag=True, help="Ignore cached results, re-run all checkers")
@click.option("--headed", is_flag=True, help="Run browser in headed mode (visible window)")
@click.option("--output-dir", "-o", type=click.Path(), default=None, help="Output directory")
@click.option(
    "--model", "-m",
    type=str,
    default=None,
    help="Claude model to use (e.g., claude-sonnet-4-20250514, claude-opus-4-6)",
)
@click.option(
    "--oauth-token",
    type=str,
    default=None,
    help="Anthropic OAuth token (from Claude Code / Claude Max)",
)
@click.option(
    "--original-url",
    type=str,
    default=None,
    help="Override original site URL",
)
@click.option(
    "--migrated-url",
    type=str,
    default=None,
    help="Override migrated site URL",
)
def audit(checkers, no_cache, headed, output_dir, model, oauth_token, original_url, migrated_url):
    """Run a full or partial migration audit."""
    settings = Settings()

    if no_cache:
        settings.cache_enabled = False
    if output_dir:
        settings.output_dir = Path(output_dir)
    if model:
        settings.llm_model = model
    if oauth_token:
        settings.anthropic_oauth_token = oauth_token
    if original_url:
        settings.original_url = original_url
    if migrated_url:
        settings.migrated_url = migrated_url

    runner = AuditRunner(settings, headed=headed)
    checkers_list = list(checkers) if checkers else None
    asyncio.run(runner.run(checkers_list))


@main.command(name="clear-cache")
@click.option("--output-dir", "-o", type=click.Path(), default="./output")
def clear_cache(output_dir):
    """Clear all cached audit results."""
    from src.cache.manager import CacheManager

    cache = CacheManager(Path(output_dir) / "cache")
    cache.invalidate_all()
    Console().print("[green]Cache cleared.[/green]")


@main.command(name="list-checkers")
def list_checkers():
    """List all available audit checkers."""
    console = Console()
    console.print("\n[bold]Available checkers:[/bold]\n")
    for name, cls in CHECKER_REGISTRY.items():
        doc = cls.__doc__ or cls.checker_type.value
        console.print(f"  [cyan]{name:15s}[/cyan] {doc}")
    console.print()


if __name__ == "__main__":
    main()

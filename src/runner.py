from __future__ import annotations

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from config.settings import Settings
from src.browser.context import BrowserManager
from src.cache.manager import CacheManager
from src.checkers.base import BaseChecker
from src.checkers.content import ContentChecker
from src.checkers.forms import FormsChecker
from src.checkers.links import LinkChecker
from src.checkers.llm_review import LLMReviewChecker
from src.checkers.navigation import NavigationChecker
from src.checkers.performance import PerformanceChecker
from src.checkers.responsive import ResponsiveChecker
from src.checkers.seo import SEOChecker
from src.checkers.visual import VisualChecker
from src.llm.client import LLMClient
from src.llm.synthesizer import Synthesizer
from src.output.markdown import MarkdownRenderer

CHECKER_REGISTRY: dict[str, type[BaseChecker]] = {
    "visual": VisualChecker,
    "links": LinkChecker,
    "seo": SEOChecker,
    "content": ContentChecker,
    "navigation": NavigationChecker,
    "forms": FormsChecker,
    "responsive": ResponsiveChecker,
    "performance": PerformanceChecker,
    "llm_review": LLMReviewChecker,
}


class AuditRunner:
    def __init__(self, settings: Settings, headed: bool = False):
        self.settings = settings
        self.headed = headed
        self.cache = (
            CacheManager(settings.output_dir / "cache")
            if settings.cache_enabled
            else None
        )
        self.console = Console()

    async def run(self, checkers: list[str] | None = None) -> str:
        """Run the full audit pipeline. Returns path to generated report."""
        checkers_to_run = checkers or list(CHECKER_REGISTRY.keys())
        invalid = [c for c in checkers_to_run if c not in CHECKER_REGISTRY]
        if invalid:
            self.console.print(
                f"[red]Unknown checkers: {', '.join(invalid)}. "
                f"Available: {', '.join(CHECKER_REGISTRY.keys())}[/red]"
            )
            return ""

        self.settings.output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        self.console.print(
            f"\n[bold]Auditing migration: [cyan]{self.settings.original_url}[/cyan] "
            f"→ [cyan]{self.settings.migrated_url}[/cyan][/bold]\n"
        )

        async with BrowserManager(
            headless=not self.headed, timeout=self.settings.page_timeout
        ) as browser:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=self.console,
            ) as progress:
                task = progress.add_task(
                    "Running audit checkers...", total=len(checkers_to_run)
                )

                for name in checkers_to_run:
                    progress.update(
                        task, description=f"Running [bold]{name}[/bold] checker..."
                    )

                    cache_params = {
                        "urls": [self.settings.original_url, self.settings.migrated_url]
                    }
                    if self.cache:
                        cached = self.cache.get(name, cache_params)
                        if cached:
                            self.console.print(
                                f"  [dim]Using cached result for {name}[/dim]"
                            )
                            results.append(cached)
                            progress.advance(task)
                            continue

                    checker_cls = CHECKER_REGISTRY[name]
                    checker = checker_cls(browser=browser, settings=self.settings)
                    try:
                        result = await checker.run()
                        results.append(result)
                        self.console.print(
                            f"  [green]✓[/green] {name}: {result.summary}"
                        )
                        if self.cache:
                            self.cache.put(result, cache_params)
                    except Exception as e:
                        self.console.print(f"  [red]✗[/red] {name}: {e}")

                    progress.advance(task)

        if not results:
            self.console.print("[red]No checker results collected. Aborting.[/red]")
            return ""

        # Extract screenshot pairs for visual comparison
        screenshot_pairs: list[dict] = []
        for r in results:
            if r.checker_type.value == "visual":
                screenshot_pairs = r.raw_data.get("screenshot_pairs", [])

        renderer = MarkdownRenderer(self.settings.output_dir / "reports")

        has_auth = self.settings.anthropic_api_key or self.settings.anthropic_oauth_token
        if not has_auth:
            self.console.print(
                "\n[yellow]No ANTHROPIC_API_KEY or ANTHROPIC_OAUTH_TOKEN set. "
                "Generating raw data report without LLM synthesis.[/yellow]"
            )
            return self._render_raw(results, renderer)

        auth_method = "OAuth token" if self.settings.anthropic_oauth_token else "API key"
        self.console.print(
            f"\n[bold]Synthesizing report with Claude ({auth_method})...[/bold]"
        )
        try:
            llm = LLMClient(
                api_key=self.settings.anthropic_api_key,
                oauth_token=self.settings.anthropic_oauth_token,
                model=self.settings.llm_model,
            )
            synthesizer = Synthesizer(llm, log=self.console.print)
            report_markdown = synthesizer.synthesize(results, screenshot_pairs)
            report_path = renderer.render(report_markdown)
            self.console.print(
                f"\n[bold green]Report generated: {report_path}[/bold green]"
            )
            return str(report_path)
        except Exception as e:
            self.console.print(f"\n[red]LLM synthesis failed: {e}[/red]")
            self.console.print("[yellow]Falling back to raw data report...[/yellow]")
            return self._render_raw(results, renderer)

    def _render_raw(self, results: list, renderer: MarkdownRenderer) -> str:
        raw_results = [
            {
                "type": r.checker_type.value,
                "summary": r.summary,
                "data": r.raw_data,
            }
            for r in results
        ]
        report_path = renderer.render_raw_fallback(raw_results)
        self.console.print(
            f"\n[bold green]Raw report generated: {report_path}[/bold green]"
        )
        return str(report_path)

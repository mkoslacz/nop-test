# nop-test

Automated migration audit tool that compares a rewritten homepage (`nop-go.noclegi.pl`) against the original production site (`noclegi.pl`). Runs 8 independent checkers via headless Chromium, then synthesizes findings into a structured, developer-friendly bug report using the Claude API.

Built to validate that the migrated homepage is a **seamless replacement** — visually identical, functionally equivalent, with all links to non-migrated pages pointing back to the original domain.

## What it checks

| Checker | Description |
|---------|-------------|
| `visual` | Full-page screenshots at 3 viewports (mobile, tablet, desktop) with pixel-level diff via Pillow |
| `links` | Broken links (HTTP 4xx/5xx), misconfigured links pointing to `nop-go` subpages, missing/extra links vs original |
| `seo` | Title, meta description, canonical URL, Open Graph, JSON-LD schemas, hreflang, heading hierarchy |
| `content` | Text content comparison by section (header, nav, main, footer), element count diff |
| `navigation` | Menu/dropdown interaction testing, language selector, currency switcher presence |
| `forms` | Search form: location autocomplete, date picker, guest selector, form submission redirect target |
| `responsive` | Horizontal overflow, mobile hamburger menu, oversized images, small touch targets |
| `performance` | DOM Content Loaded, TTFB, LCP, total resources, transfer size — flags regressions >20% |

## Output

A Markdown report with issues categorized by severity:

- **Critical** — blocks launch (broken links, misconfigured internal links, missing canonical)
- **Major** — significant user-visible regressions (SEO gaps, layout breaks)
- **Minor** — cosmetic differences (color, spacing, typography)
- **Info** — observations and improvements

Each issue includes: description, step-by-step reproduction, expected vs actual behavior, affected viewports, and related URLs.

When the Claude API key is configured, the report is synthesized by an LLM that also performs visual screenshot comparison. Without an API key, a raw data report is generated instead.

## Requirements

- Python 3.11+
- Chromium (installed automatically via Playwright)
- [Anthropic API key](https://console.anthropic.com/) (optional — for LLM-powered report synthesis)

## Setup

```bash
# Clone
git clone https://github.com/mkoslacz/nop-test.git
cd nop-test

# Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium

# (Optional) Configure API key for LLM synthesis
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

## Usage

```bash
# Full audit with all 8 checkers
nop-test audit

# Run specific checkers only
nop-test audit -c links -c seo

# Fresh run ignoring cache
nop-test audit --no-cache

# Use a different Claude model
nop-test audit --model claude-opus-4-6

# Debug with visible browser window
nop-test audit -c visual --headed

# Override URLs
nop-test audit --original-url https://noclegi.pl --migrated-url https://nop-go.noclegi.pl

# Clear cached results
nop-test clear-cache

# List available checkers
nop-test list-checkers
```

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | _(none)_ | Anthropic API key for LLM synthesis |
| `NOP_ORIGINAL_URL` | `https://noclegi.pl` | Original site URL |
| `NOP_MIGRATED_URL` | `https://nop-go.noclegi.pl` | Migrated site URL |
| `NOP_OUTPUT_DIR` | `./output` | Output directory for reports and screenshots |
| `NOP_CACHE_ENABLED` | `true` | Cache checker results between runs |
| `NOP_LLM_MODEL` | `claude-sonnet-4-20250514` | Claude model for synthesis |

## Project structure

```
nop-test/
├── config/
│   ├── settings.py          # Pydantic settings
│   └── default.toml         # Default config values
├── src/
│   ├── cli.py               # Click CLI
│   ├── runner.py             # Orchestrator
│   ├── models/               # Data classes (AuditResult, Issue, Report)
│   ├── browser/              # Playwright browser management
│   ├── checkers/             # 8 audit checkers (each independent)
│   ├── llm/                  # Claude API client + 2-stage synthesizer
│   ├── cache/                # JSON result caching with TTL
│   └── output/               # Markdown report renderer
└── output/                   # Runtime output (gitignored)
    ├── screenshots/          # Captured + diff screenshots
    ├── cache/                # Cached checker results
    └── reports/              # Generated Markdown reports
```

## How synthesis works

1. **Stage 1 — Visual analysis**: Each screenshot pair (original vs migrated, per viewport) is sent to Claude Vision for qualitative comparison
2. **Stage 2 — Full synthesis**: All raw checker data + visual analyses are combined into a single prompt; Claude generates the final structured report with severity-categorized issues and reproduction steps

If the raw data exceeds token limits, large link lists are automatically truncated while preserving critical findings (broken/misconfigured links).

## License

MIT

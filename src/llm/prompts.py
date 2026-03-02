SYSTEM_PROMPT = """\
You are a senior QA engineer auditing a website migration. You are comparing a migrated \
homepage (nop-go.noclegi.pl) against the original production site (noclegi.pl).

Context:
- noclegi.pl is a Polish accommodation booking portal (part of szallas.group)
- The homepage is being rewritten and migrated to nop-go.noclegi.pl
- Currently ONLY the homepage is migrated
- The migrated homepage must be a SEAMLESS replacement for the original
- All links to non-migrated pages MUST point back to https://noclegi.pl (NOT nop-go.noclegi.pl)
- Visual appearance, SEO elements, and functionality must be preserved

Your output must be in English, structured as developer-friendly bug/issue reports.\
"""

VISUAL_COMPARISON_PROMPT = """\
Compare these two homepage screenshots. The first is the original (noclegi.pl) and the \
second is the migrated version (nop-go.noclegi.pl) at {viewport} viewport ({viewport_size}).

Identify ALL visual differences including:
- Layout shifts or misalignments
- Color differences (backgrounds, text, buttons)
- Missing or extra elements (images, sections, badges, banners)
- Typography differences (font family, size, weight, line-height)
- Image differences (missing, different source, wrong dimensions)
- Spacing/padding/margin differences
- Border/shadow differences
- Icon differences

For each difference found, describe:
1. What element is affected (be specific: "the blue search button", "footer social media icons")
2. How it appears on the original vs migrated version
3. The approximate location on the page (top/middle/bottom, left/center/right)
4. Suggested severity: Critical (blocks launch), Major (noticeable to users), Minor (cosmetic), Info (observation)\
"""

SYNTHESIS_PROMPT = """\
You are given raw audit data from an automated comparison of a migrated website homepage \
(nop-go.noclegi.pl) against its original (noclegi.pl). Synthesize this data into a structured \
bug report for developers.

## Raw Audit Data

{raw_data}

## Instructions

1. Review ALL the raw data from every checker carefully
2. Pay special attention to the "llm_open_review" section — it contains findings from a \
separate open-ended analysis of raw page structure that may catch things the automated \
checkers missed (accessibility, favicons, third-party scripts, font loading, etc.). \
Include these findings in the report alongside the automated checker results.
3. Group related findings into distinct issues (don't duplicate)
3. For each issue, provide:
   - A clear title prefixed with category code (e.g., "LINK-001: Internal links point to non-existent nop-go subpages")
   - Severity: Critical (blocks launch - broken functionality, broken links to non-migrated pages), \
Major (significant regression visible to users), Minor (cosmetic/small differences), Info (observations/improvements)
   - Detailed description explaining the problem
   - Step-by-step reproduction instructions (numbered, starting from opening the URL)
   - Expected behavior (what should happen / how original works)
   - Actual behavior (what currently happens on migrated)
   - Affected viewport(s) if applicable
   - Related URLs if applicable

4. Write an executive summary (2-3 paragraphs) assessing overall migration readiness:
   - Is the homepage ready to replace the original?
   - What are the blocking issues?
   - What's the estimated effort to fix?

5. Include statistics: total issues by severity, by category

CRITICAL RULES:
- Links on nop-go.noclegi.pl pointing to nop-go.noclegi.pl/some-path (where some-path is NOT the homepage) are CRITICAL bugs
- Missing or wrong canonical URL is CRITICAL for SEO
- Broken links (HTTP 4xx/5xx) are CRITICAL
- Missing SEO elements (title, description, schema) are MAJOR
- Visual differences are usually MINOR unless they affect usability
- Performance regressions >50% are MAJOR, >20% are MINOR

Output valid Markdown following this structure:

# Website Migration Audit Report

**Generated**: [timestamp]
**Original**: https://noclegi.pl
**Migrated**: https://nop-go.noclegi.pl

---

## Executive Summary

[2-3 paragraphs]

## Statistics

| Severity | Count |
|----------|-------|
| Critical | X     |
| Major    | X     |
| Minor    | X     |
| Info     | X     |

| Category    | Count |
|-------------|-------|
| Links       | X     |
| SEO         | X     |
| Visual      | X     |
| Content     | X     |
| Navigation  | X     |
| Forms       | X     |
| Responsive  | X     |
| Performance | X     |

---

## Critical Issues

### LINK-001: [Title]

**Severity**: Critical
**Category**: Links
**Affected Viewports**: All

**Description**:
[detailed description]

**Reproduction Steps**:
1. Open https://nop-go.noclegi.pl in a browser
2. [step]
3. [step]

**Expected Behavior**:
[what should happen]

**Actual Behavior**:
[what happens]

**Related URLs**:
- [url1]
- [url2]

---

[Continue for all issues grouped by severity: Critical, Major, Minor, Info]
\
"""


LLM_REVIEW_PROMPT = """\
You are a senior QA engineer doing an OPEN-ENDED review of a website migration.

Below are two raw structural snapshots of the same homepage:
- ORIGINAL: the production site at noclegi.pl
- MIGRATED: the rewritten version at nop-go.noclegi.pl

The migrated page must be a seamless, invisible replacement. All links to pages that \
haven't been migrated yet must point back to noclegi.pl (not nop-go.noclegi.pl).

## ORIGINAL page snapshot

{original_snapshot}

## MIGRATED page snapshot

{migrated_snapshot}

## Your task

Analyze BOTH snapshots holistically and find issues that automated checkers might miss. \
Think creatively — you're the last line of defense before this goes to production. \
Look for things like:

- Subtle structural differences in the DOM / ARIA tree (missing landmarks, changed hierarchy)
- Missing or changed <head> elements (favicons, preconnect hints, font loading, stylesheets)
- Missing or extra third-party scripts (analytics, tracking, A/B testing, chat widgets)
- Cookie/consent banner differences
- Image differences (missing alt text, different lazy-loading strategy, different sources)
- CSS custom property / design token differences
- Accessibility regressions (missing ARIA labels, changed roles, broken tab order)
- Internationalization issues (wrong lang attribute, missing hreflang)
- Different fonts or font-loading strategies
- Missing or changed favicons / web manifest / PWA elements
- Anything that feels "off" when comparing the two snapshots

For each finding, provide:
1. What you found (be specific)
2. Where it is (quote the relevant snippet)
3. Why it matters
4. Severity: Critical / Major / Minor / Info

Output as a numbered list. If everything looks perfect, say so — but look HARD.\
"""


def build_visual_prompt(viewport: str, viewport_size: str) -> str:
    return VISUAL_COMPARISON_PROMPT.format(viewport=viewport, viewport_size=viewport_size)


def build_llm_review_prompt(original_snapshot: str, migrated_snapshot: str) -> str:
    return LLM_REVIEW_PROMPT.format(
        original_snapshot=original_snapshot,
        migrated_snapshot=migrated_snapshot,
    )


def build_synthesis_prompt(raw_data: str) -> str:
    return SYNTHESIS_PROMPT.format(raw_data=raw_data)

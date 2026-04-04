"""Starter schema templates for Compendium projects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaTemplate:
    """A starter schema template exposed in init/settings flows."""

    template_id: str
    label: str
    description: str
    focus_areas: tuple[str, ...]
    suggested_categories: tuple[str, ...]
    page_types: tuple[str, ...]
    review_questions: tuple[str, ...]


TEMPLATES: dict[str, SchemaTemplate] = {
    "research": SchemaTemplate(
        template_id="research",
        label="Research",
        description="Best for papers, notes, experiments, and synthesis across sources.",
        focus_areas=(
            "claims and evidence",
            "methods and limitations",
            "cross-source disagreements",
            "concept and author relationships",
        ),
        suggested_categories=("concepts", "methods", "findings", "sources", "meta"),
        page_types=("concept", "method", "finding", "source-summary", "overview"),
        review_questions=(
            "What is the strongest claim supported by multiple sources?",
            "Which findings disagree, and why?",
            "What follow-up questions would reduce uncertainty?",
        ),
    ),
    "book-reading": SchemaTemplate(
        template_id="book-reading",
        label="Book Reading",
        description="Optimized for chapter notes, themes, arguments, and memorable takeaways.",
        focus_areas=(
            "chapter summaries",
            "key arguments and examples",
            "quotes and anecdotes",
            "themes that recur across chapters",
        ),
        suggested_categories=("chapters", "themes", "quotes", "people", "meta"),
        page_types=("chapter-note", "theme", "quote-bank", "person", "overview"),
        review_questions=(
            "What argument does the author repeat most often?",
            "Which chapters change the main thesis or nuance it?",
            "What ideas are worth turning into action or further reading?",
        ),
    ),
    "competitive-analysis": SchemaTemplate(
        template_id="competitive-analysis",
        label="Competitive Analysis",
        description="For market scans, vendor research, feature comparisons, and win/loss notes.",
        focus_areas=(
            "company and product profiles",
            "positioning and messaging",
            "features, gaps, and tradeoffs",
            "pricing, risks, and strategic moves",
        ),
        suggested_categories=("companies", "products", "features", "markets", "meta"),
        page_types=("company", "product", "feature-gap", "market-theme", "overview"),
        review_questions=(
            "Which competitors cluster around the same positioning?",
            "What capabilities appear frequently but remain weakly differentiated?",
            "What unanswered questions need new sources or customer evidence?",
        ),
    ),
    "personal-tracking": SchemaTemplate(
        template_id="personal-tracking",
        label="Personal Tracking",
        description="For habits, journals, health logs, retrospectives, and recurring measurements.",
        focus_areas=(
            "daily or weekly logs",
            "trend summaries",
            "triggers, causes, and interventions",
            "questions to revisit over time",
        ),
        suggested_categories=("logs", "trends", "habits", "experiments", "meta"),
        page_types=("daily-log", "trend", "habit", "experiment", "retrospective"),
        review_questions=(
            "What patterns are improving or degrading over time?",
            "Which entries are missing context or supporting evidence?",
            "What should be measured next to make decisions easier?",
        ),
    ),
    "course-notes": SchemaTemplate(
        template_id="course-notes",
        label="Course Notes",
        description="For lectures, readings, assignments, and concept reinforcement.",
        focus_areas=(
            "lecture summaries",
            "definitions and worked examples",
            "assignments and practice questions",
            "dependencies between concepts",
        ),
        suggested_categories=("lectures", "concepts", "examples", "assignments", "meta"),
        page_types=("lecture-note", "concept", "worked-example", "assignment", "overview"),
        review_questions=(
            "Which concepts recur across lectures?",
            "Where do examples clarify or contradict the abstract notes?",
            "What questions should be reviewed before the next session?",
        ),
    ),
}


def template_ids() -> list[str]:
    """Return all supported template ids in stable order."""
    return list(TEMPLATES.keys())


def get_template(template_id: str) -> SchemaTemplate:
    """Return a template, falling back to research for unknown ids."""
    return TEMPLATES.get(template_id, TEMPLATES["research"])


def generate_schema_md(template_id: str = "research", domain: str = "") -> str:
    """Generate SCHEMA.md from a template and optional domain description."""
    template = get_template(template_id)
    domain_line = domain.strip() or "General-purpose knowledge compilation."

    focus = "\n".join(f"- {item}" for item in template.focus_areas)
    categories = "\n".join(f"- `{item}`" for item in template.suggested_categories)
    page_types = "\n".join(f"- `{item}`" for item in template.page_types)
    review = "\n".join(f"- {item}" for item in template.review_questions)

    return f"""# Wiki Schema

*Auto-generated by Compendium*

## Active Template

- Template: `{template.template_id}` ({template.label})
- Purpose: {template.description}
- Domain: {domain_line}

## Directory Structure

```
wiki/
  INDEX.md          # Master index table of all articles
  CONCEPTS.md       # Concept taxonomy (hierarchical)
  CONFLICTS.md      # Detected cross-source contradictions
  SCHEMA.md         # This file — wiki format documentation
  CHANGELOG.md      # Compilation history
  HEALTH_REPORT.md  # Latest lint report
  <category>/       # Article subdirectories by category
    <article>.md    # Individual wiki articles
```

## Content Priorities

{focus}

## Suggested Categories

{categories}

## Expected Page Types

{page_types}

## Frontmatter Contract

Every wiki article should include:

```yaml
---
title: "Human readable title"
id: "stable-slug"
category: "one-of-the-template-categories"
type: "page-type"
sources:
  - ref: "raw/source-id.md"
origin: "compilation | qa-output | manual"
status: "published | draft"
created_at: "ISO-8601 timestamp"
updated_at: "ISO-8601 timestamp"
---
```

## Linking Rules

- Prefer wikilinks such as `[[article-slug]]` or `[[article-slug|Display Text]]`.
- Link all source-backed claims to `raw/` references in frontmatter.
- Add backlinks and related article sections when topics overlap.

## Index and Log Contracts

- `INDEX.md` must use the columns: `Page | Type | Summary | Sources | Updated`.
- `INDEX.md` should be grouped by category and alphabetized by page title.
- `log.md` entries must use the format `## [YYYY-MM-DD] operation | Title`.

## Review Questions

{review}
"""


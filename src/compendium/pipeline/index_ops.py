"""Index operations — verify and rebuild INDEX.md / CONCEPTS.md."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frontmatter as fm

from compendium.core.wikilinks import WIKILINK_PATTERN

if TYPE_CHECKING:
    from pathlib import Path


def _scan_wiki_articles(wiki_dir: Path) -> list[dict[str, str]]:
    """Scan wiki/ for all article files and return metadata."""
    articles: list[dict[str, str]] = []
    for md_file in wiki_dir.rglob("*.md"):
        rel = md_file.relative_to(wiki_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if md_file.name in (
            "INDEX.md",
            "CONCEPTS.md",
            "CONFLICTS.md",
            "CHANGELOG.md",
            "HEALTH_REPORT.md",
            "SCHEMA.md",
        ):
            continue

        try:
            post = fm.load(str(md_file))
            title = post.metadata.get("title", md_file.stem.replace("-", " ").title())
            category = post.metadata.get("category", "uncategorized")
            body = post.content.strip()
            first_line = ""
            for line in body.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    first_line = stripped[:100]
                    break
        except Exception:
            title = md_file.stem.replace("-", " ").title()
            category = "uncategorized"
            first_line = ""

        articles.append(
            {
                "path": str(rel),
                "slug": md_file.stem,
                "title": title,
                "category": category,
                "summary": first_line,
                "content": md_file.read_text(),
            }
        )

    return sorted(articles, key=lambda a: a["slug"])


def _parse_index_slugs(wiki_dir: Path) -> set[str]:
    """Parse INDEX.md and return the set of article slugs it references."""
    index_path = wiki_dir / "INDEX.md"
    if not index_path.exists():
        return set()

    slugs: set[str] = set()
    for match in WIKILINK_PATTERN.finditer(index_path.read_text()):
        target = match.group(1).strip()
        slug = target.split("/")[-1].replace(".md", "")
        slugs.add(slug)
    return slugs


def verify_wiki_index(wiki_dir: Path) -> dict:
    """Check INDEX.md consistency against actual wiki articles.

    Returns dict with: consistent (bool), mismatches (list of issues).
    """
    articles = _scan_wiki_articles(wiki_dir)
    article_slugs = {a["slug"] for a in articles}
    index_slugs = _parse_index_slugs(wiki_dir)

    mismatches: list[dict[str, str]] = []

    # Articles in wiki/ but not in INDEX.md
    for slug in sorted(article_slugs - index_slugs):
        mismatches.append(
            {
                "type": "MISSING_FROM_INDEX",
                "detail": f"Article '{slug}' exists in wiki/ but not in INDEX.md",
            }
        )

    # Entries in INDEX.md but no corresponding article
    for slug in sorted(index_slugs - article_slugs):
        mismatches.append(
            {
                "type": "EXTRA_IN_INDEX",
                "detail": f"INDEX.md references '{slug}' but no article file found",
            }
        )

    # Check CONCEPTS.md existence
    if not (wiki_dir / "CONCEPTS.md").exists() and articles:
        mismatches.append(
            {
                "type": "MISSING_FILE",
                "detail": "CONCEPTS.md is missing",
            }
        )

    return {
        "consistent": len(mismatches) == 0,
        "mismatches": mismatches,
        "article_count": len(article_slugs),
        "index_count": len(index_slugs),
    }


def rebuild_wiki_index(wiki_dir: Path) -> dict:
    """Rebuild INDEX.md and CONCEPTS.md from wiki/ article scan.

    Returns dict with: articles (count), concepts (count).
    """
    articles = _scan_wiki_articles(wiki_dir)

    # Extract concepts from articles
    all_concepts: dict[str, dict] = {}
    for article in articles:
        try:
            post = fm.loads(article["content"])
            category = post.metadata.get("category", "concepts")
            tags = post.metadata.get("tags", [])
            for tag in tags:
                key = tag.lower()
                if key not in all_concepts:
                    all_concepts[key] = {
                        "canonical_name": tag,
                        "category": category,
                        "source_count": 0,
                        "aliases": [tag.lower()],
                        "should_generate_article": True,
                    }
                all_concepts[key]["source_count"] += 1
        except Exception:
            pass

    # Also extract concept names from article titles
    for article in articles:
        key = article["title"].lower()
        if key not in all_concepts:
            all_concepts[key] = {
                "canonical_name": article["title"],
                "category": article["category"],
                "source_count": 1,
                "aliases": [],
                "should_generate_article": True,
            }

    from compendium.pipeline.steps import step_build_index

    article_dicts = [{"path": f"wiki/{a['path']}", "content": a["content"]} for a in articles]
    concept_list = list(all_concepts.values())

    index_files = step_build_index(article_dicts, concept_list, "Index rebuilt from wiki scan")

    for filename, content in index_files.items():
        (wiki_dir / filename).write_text(content)

    return {
        "articles": len(articles),
        "concepts": len(all_concepts),
    }

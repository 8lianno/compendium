"""Wiki linting — health checks for broken links, orphans, staleness, gaps, contradictions."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter

from compendium.core.wikilinks import WIKILINK_PATTERN

if TYPE_CHECKING:
    from pathlib import Path


class LintIssue:
    """A single lint issue found in the wiki."""

    def __init__(
        self,
        severity: str,
        category: str,
        location: str,
        description: str,
        suggestion: str = "",
    ) -> None:
        self.severity = severity  # critical | warning | info
        self.category = category  # broken_link | orphan | stale | gap | contradiction
        self.location = location  # article path or name
        self.description = description
        self.suggestion = suggestion

    def __repr__(self) -> str:
        return f"[{self.severity.upper()}] {self.category}: {self.description} ({self.location})"


class LintReport:
    """Collection of lint issues with severity counts."""

    def __init__(self) -> None:
        self.issues: list[LintIssue] = []

    def add(self, issue: LintIssue) -> None:
        self.issues.append(issue)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")

    @property
    def total(self) -> int:
        return len(self.issues)

    def to_markdown(self) -> str:
        """Render the report as HEALTH_REPORT.md content."""
        now = datetime.now(UTC).isoformat()
        lines = [
            "---\n",
            'title: "Wiki Health Report"\n',
            'id: "health-report"\n',
            'category: "meta"\n',
            'type: "health-report"\n',
            'origin: "lint"\n',
            'status: "published"\n',
            f'updated_at: "{now}"\n',
            "---\n\n",
            "# Wiki Health Report\n\n",
            f"*Generated: {now}*\n",
            f"*Issues: {self.total} "
            f"({self.critical_count} critical, "
            f"{self.warning_count} warning, "
            f"{self.info_count} info)*\n\n",
        ]

        if not self.issues:
            lines.append("No issues found. Your wiki is healthy!\n")
            return "".join(lines)

        # Group by severity
        for severity in ("critical", "warning", "info"):
            items = [i for i in self.issues if i.severity == severity]
            if not items:
                continue

            lines.append(f"## {severity.title()}\n\n")
            for issue in items:
                lines.append(f"### {issue.category.replace('_', ' ').title()}\n")
                lines.append(f"- **Location:** {issue.location}\n")
                lines.append(f"- **Issue:** {issue.description}\n")
                if issue.suggestion:
                    lines.append(f"- **Suggestion:** {issue.suggestion}\n")
                lines.append("\n")

        return "".join(lines)


def lint_wiki(
    wiki_dir: Path,
    raw_dir: Path | None = None,
    llm: object | None = None,
) -> LintReport:
    """Run all health checks on the wiki.

    Checks:
    1. Broken internal links (wikilinks to non-existent articles)
    2. Orphan articles (no inbound backlinks)
    3. Stale articles (source updated but wiki not recompiled)
    4. Coverage gaps (concepts mentioned frequently but no dedicated article)
    5. Structural issues (missing index.md, etc.)
    6. Contradictions (if llm provided — deep mode)
    """
    report = LintReport()

    # Collect all article paths and slugs
    articles: dict[str, Path] = {}  # slug -> path
    article_contents: dict[str, str] = {}  # slug -> content

    for md_file in wiki_dir.rglob("*.md"):
        rel = md_file.relative_to(wiki_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if md_file.name in (
            "INDEX.md",
            "CONCEPTS.md",
            "index.md",
            "concepts.md",
            "CONFLICTS.md",
            "CHANGELOG.md",
            "HEALTH_REPORT.md",
            "SCHEMA.md",
            "overview.md",
            "log.md",
        ):
            continue
        slug = md_file.stem
        articles[slug] = md_file
        article_contents[slug] = md_file.read_text()

    # -- Check 1: Broken links --
    _check_broken_links(articles, article_contents, report)

    # -- Check 2: Orphan articles --
    _check_orphans(articles, article_contents, report)

    # -- Check 3: Stale articles --
    if raw_dir:
        _check_staleness(articles, wiki_dir, raw_dir, report)

    # -- Check 4: Coverage gaps --
    _check_coverage_gaps(articles, article_contents, wiki_dir, report)

    # -- Check 5: Missing cross-references --
    _check_missing_crossrefs(articles, article_contents, report)

    # -- Check 6: Structural checks --
    _check_structure(wiki_dir, report)

    # -- Check 7: Existing conflicts file --
    _check_conflict_file(wiki_dir, report)

    # -- Check 8: Suggest questions and sources --
    _suggest_investigations(articles, article_contents, wiki_dir, report)

    # -- Check 9: Contradictions (deep mode) --
    if llm is not None:
        import asyncio

        asyncio.run(_check_contradictions(article_contents, llm, report))

    return report


def _check_broken_links(
    articles: dict[str, Path],
    article_contents: dict[str, str],
    report: LintReport,
) -> None:
    """Find wikilinks that don't resolve to any article."""
    for slug, content in article_contents.items():
        links = WIKILINK_PATTERN.findall(content)
        for target, _display in links:
            target = target.strip()
            # Skip raw/ references
            if target.startswith("raw/"):
                continue
            # Normalize: remove wiki/ prefix, .md suffix, path components
            target_slug = target.split("/")[-1].replace(".md", "").strip()
            if target_slug and target_slug not in articles:
                report.add(
                    LintIssue(
                        severity="critical",
                        category="broken_link",
                        location=slug,
                        description=f"Link [[{target}]] does not resolve to any article",
                        suggestion=f"Create article '{target_slug}' or fix the link",
                    )
                )


def _check_orphans(
    articles: dict[str, Path],
    article_contents: dict[str, str],
    report: LintReport,
) -> None:
    """Find articles with zero inbound backlinks."""
    # Count inbound links for each article
    inbound: dict[str, int] = {slug: 0 for slug in articles}

    for _slug, content in article_contents.items():
        links = WIKILINK_PATTERN.findall(content)
        for target, _display in links:
            target_slug = target.strip().split("/")[-1].replace(".md", "").strip()
            if target_slug in inbound:
                inbound[target_slug] += 1

    for slug, count in inbound.items():
        if count == 0:
            report.add(
                LintIssue(
                    severity="warning",
                    category="orphan",
                    location=slug,
                    description=f"Article '{slug}' has no inbound backlinks",
                    suggestion="Add references from related articles",
                )
            )


def _check_staleness(
    articles: dict[str, Path],
    wiki_dir: Path,
    raw_dir: Path,
    report: LintReport,
) -> None:
    """Find articles whose source dependencies have been modified since compilation."""
    for slug, path in articles.items():
        try:
            post = frontmatter.load(str(path))
            sources = post.metadata.get("sources", [])
            article_mtime = path.stat().st_mtime

            for source in sources:
                source_ref = source.get("ref", "") if isinstance(source, dict) else str(source)
                # Resolve source path
                if source_ref.startswith("raw/"):
                    source_path = raw_dir.parent / source_ref
                else:
                    source_path = raw_dir / source_ref

                if source_path.exists() and source_path.stat().st_mtime > article_mtime:
                    report.add(
                        LintIssue(
                            severity="info",
                            category="stale",
                            location=slug,
                            description=f"Source '{source_ref}' modified after compilation",
                            suggestion="Run `compendium update` to refresh",
                        )
                    )
                    break  # One stale source is enough
        except Exception:
            continue


def _check_coverage_gaps(
    articles: dict[str, Path],
    article_contents: dict[str, str],
    wiki_dir: Path,
    report: LintReport,
) -> None:
    """Find concepts mentioned frequently but without dedicated articles."""
    # Count concept mentions across all articles
    concept_mentions: dict[str, int] = {}
    all_text = " ".join(article_contents.values()).lower()

    # Extract potential concepts from CONCEPTS.md
    concepts_path = _resolve_meta_page(wiki_dir, "concepts.md", "CONCEPTS.md")
    if not concepts_path.exists():
        return

    for line in concepts_path.read_text().split("\n"):
        match = re.search(r"\*\*([^*]+)\*\*", line)
        if match:
            concept = match.group(1).strip()
            concept_lower = concept.lower()
            count = all_text.count(concept_lower)
            if count >= 3:
                # Check if there's a dedicated article
                concept_slug = re.sub(r"[^\w\s-]", "", concept_lower)
                concept_slug = re.sub(r"[\s_]+", "-", concept_slug).strip("-")
                if concept_slug not in articles:
                    concept_mentions[concept] = count

    for concept, count in sorted(concept_mentions.items(), key=lambda x: -x[1]):
        report.add(
            LintIssue(
                severity="info",
                category="coverage_gap",
                location=concepts_path.name,
                description=f"'{concept}' mentioned {count} times but has no dedicated article",
                suggestion=f"Create article: '{concept}' — referenced across multiple articles",
            )
        )


def _check_missing_crossrefs(
    articles: dict[str, Path],
    article_contents: dict[str, str],
    report: LintReport,
) -> None:
    """Find article mentions that are not wired with explicit wikilinks."""
    article_titles: dict[str, str] = {}
    linked_targets: dict[str, set[str]] = {}

    for slug, path in articles.items():
        try:
            post = frontmatter.load(str(path))
            article_titles[slug] = str(post.metadata.get("title", slug.replace("-", " ").title()))
        except Exception:
            article_titles[slug] = slug.replace("-", " ").title()

    for slug, content in article_contents.items():
        linked_targets[slug] = {
            target.strip().split("/")[-1].replace(".md", "").strip()
            for target, _display in WIKILINK_PATTERN.findall(content)
            if not target.startswith("raw/")
        }

    for slug, content in article_contents.items():
        lowered = content.lower()
        issues_for_article = 0

        for target_slug, title in article_titles.items():
            if target_slug == slug or target_slug in linked_targets[slug]:
                continue

            title_lower = title.lower()
            slug_phrase = target_slug.replace("-", " ")
            if title_lower in lowered or slug_phrase in lowered:
                report.add(
                    LintIssue(
                        severity="info",
                        category="missing_crossref",
                        location=slug,
                        description=f"Mention of '{title}' is not linked",
                        suggestion=f"Add [[{target_slug}|{title}]] to connect related pages",
                    )
                )
                issues_for_article += 1
                if issues_for_article >= 5:
                    break


def _suggest_investigations(
    articles: dict[str, Path],
    article_contents: dict[str, str],
    wiki_dir: Path,
    report: LintReport,
) -> None:
    """Suggest new questions to explore and sources to look for."""
    " ".join(article_contents.values()).lower()

    # Find concepts that are mentioned but underexplored (few words about them)
    concepts_path = _resolve_meta_page(wiki_dir, "concepts.md", "CONCEPTS.md")
    if concepts_path.exists():
        for line in concepts_path.read_text().split("\n"):
            match = re.search(r"\*\*([^*]+)\*\*", line)
            if not match:
                continue
            concept = match.group(1).strip()
            concept_lower = concept.lower()
            # If concept has an article, check if it's very short
            concept_slug = re.sub(r"[^\w\s-]", "", concept_lower)
            concept_slug = re.sub(r"[\s_]+", "-", concept_slug).strip("-")
            if concept_slug in articles:
                content = article_contents[concept_slug]
                word_count = len(content.split())
                if word_count < 150:
                    report.add(LintIssue(
                        severity="info",
                        category="suggestion",
                        location=concept_slug,
                        description=f"'{concept}' article is thin ({word_count} words)",
                        suggestion=f"Look for more sources about {concept} to enrich this page",
                    ))

    # Suggest questions based on article pairs that don't reference each other
    slugs = list(articles.keys())
    if len(slugs) >= 4:
        # Find hub articles (most wikilinks)
        from compendium.core.wikilinks import WIKILINK_PATTERN

        link_counts = {}
        for slug, content in article_contents.items():
            link_counts[slug] = len(WIKILINK_PATTERN.findall(content))

        hubs = sorted(link_counts.items(), key=lambda x: -x[1])[:3]
        for hub_slug, count in hubs:
            if count > 5:
                report.add(LintIssue(
                    severity="info",
                    category="suggestion",
                    location=hub_slug,
                    description=f"'{hub_slug}' is a hub ({count} outbound links)",
                    suggestion=f"Consider asking: 'What are the key debates around {hub_slug}?'",
                ))


def _check_structure(wiki_dir: Path, report: LintReport) -> None:
    """Check for missing structural files."""
    required = [
        ("index.md", "INDEX.md"),
        ("concepts.md", "CONCEPTS.md"),
    ]
    for preferred, legacy in required:
        if not _resolve_meta_page(wiki_dir, preferred, legacy).exists():
            report.add(
                LintIssue(
                    severity="warning",
                    category="structure",
                    location=preferred,
                    description=f"{preferred} is missing",
                    suggestion="Run `compendium rebuild-index` to regenerate",
                )
            )


def _check_conflict_file(wiki_dir: Path, report: LintReport) -> None:
    """Surface existing entries from CONFLICTS.md during lint runs."""
    conflicts_path = wiki_dir / "CONFLICTS.md"
    if not conflicts_path.exists():
        return

    content = conflicts_path.read_text()
    if "No conflicts detected" in content:
        return

    headings = re.findall(r"^###\s+(.+)$", content, re.MULTILINE)
    if not headings:
        return

    for heading in headings:
        report.add(
            LintIssue(
                severity="warning",
                category="contradiction",
                location="CONFLICTS.md",
                description=f"Unresolved conflict recorded: {heading}",
                suggestion="Review CONFLICTS.md and reconcile or annotate the competing claims",
            )
        )


def _resolve_meta_page(wiki_dir: Path, preferred: str, legacy: str) -> Path:
    """Resolve a canonical wiki meta page with legacy uppercase fallback."""
    preferred_path = wiki_dir / preferred
    if preferred_path.exists():
        return preferred_path
    legacy_path = wiki_dir / legacy
    if legacy_path.exists():
        return legacy_path
    return preferred_path


async def _check_contradictions(
    article_contents: dict[str, str],
    llm: object,
    report: LintReport,
) -> None:
    """LLM-based contradiction detection between articles (deep mode)."""
    import json

    from compendium.llm.provider import CompletionRequest, Message

    slugs = list(article_contents.keys())
    if len(slugs) < 2:
        return

    # Compare pairs sharing common terms (simple pre-filter)
    pairs: list[tuple[str, str]] = []
    for i in range(len(slugs)):
        words_i = set(article_contents[slugs[i]].lower().split())
        for j in range(i + 1, len(slugs)):
            words_j = set(article_contents[slugs[j]].lower().split())
            overlap = len(words_i & words_j)
            if overlap > 20:  # Enough shared vocabulary
                pairs.append((slugs[i], slugs[j]))

    # Limit to 10 pairs
    for slug_a, slug_b in pairs[:10]:
        content_a = article_contents[slug_a][:1500]
        content_b = article_contents[slug_b][:1500]

        prompt = (
            f"Compare these two wiki articles for contradictions.\n\n"
            f"## Article A: {slug_a}\n{content_a}\n\n"
            f"## Article B: {slug_b}\n{content_b}\n\n"
            f"Respond with JSON: "
            f'{{"contradiction": true/false, "explanation": "..."}}'
        )

        try:
            response = await llm.complete(  # type: ignore[union-attr]
                CompletionRequest(
                    messages=[Message(role="user", content=prompt)],
                    system_prompt="Detect contradictions. Respond with JSON only.",
                    max_tokens=300,
                    temperature=0.1,
                )
            )
            data = json.loads(response.content)
            if data.get("contradiction"):
                report.add(
                    LintIssue(
                        severity="warning",
                        category="contradiction",
                        location=f"{slug_a} vs {slug_b}",
                        description=data.get("explanation", "Contradiction detected"),
                        suggestion="Review and resolve the conflicting claims",
                    )
                )
        except Exception:
            continue

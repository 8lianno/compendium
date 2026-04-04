"""Feedback filing — file Q&A outputs back into the wiki."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter

from compendium.ingest.dedup import text_hash

if TYPE_CHECKING:
    from pathlib import Path

    from compendium.core.wiki_fs import WikiFileSystem


def _detect_category(content: str, concepts_path: Path) -> str:
    """Auto-detect the best category by matching content against CONCEPTS.md."""
    if not concepts_path.exists():
        return "filed"

    concepts_text = concepts_path.read_text()
    content_lower = content.lower()

    # Extract categories and their concepts from CONCEPTS.md
    best_category = "filed"
    best_score = 0

    current_category = ""
    for line in concepts_text.split("\n"):
        if line.startswith("## "):
            current_category = line[3:].strip().lower()
        elif line.startswith("- **") and current_category:
            # Extract concept name
            match = re.search(r"\*\*([^*]+)\*\*", line)
            if match:
                concept = match.group(1).lower()
                if concept in content_lower:
                    score = content_lower.count(concept)
                    if score > best_score:
                        best_score = score
                        best_category = current_category

    return best_category


def _find_similar_article(title: str, wiki_dir: Path) -> Path | None:
    """Check if a similar article already exists (by title similarity)."""
    title_words = set(re.findall(r"\w+", title.lower()))
    if not title_words:
        return None

    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name.startswith(".") or any(
            p.startswith(".") for p in md_file.relative_to(wiki_dir).parts
        ):
            continue
        try:
            post = frontmatter.load(str(md_file))
            existing_title = post.metadata.get("title", md_file.stem)
            existing_words = set(re.findall(r"\w+", existing_title.lower()))
            if existing_words and len(title_words & existing_words) / len(title_words) > 0.6:
                return md_file
        except Exception:
            continue
    return None


def _insert_backlinks(filed_path: Path, wiki_dir: Path) -> int:
    """Add backlinks from existing articles that reference concepts in the filed article."""
    filed_post = frontmatter.load(str(filed_path))
    filed_title = filed_post.metadata.get("title", filed_path.stem)
    filed_slug = filed_path.stem
    backlinks_added = 0

    for md_file in wiki_dir.rglob("*.md"):
        if md_file == filed_path:
            continue
        if any(p.startswith(".") for p in md_file.relative_to(wiki_dir).parts):
            continue
        if md_file.name in ("INDEX.md", "CONCEPTS.md", "CONFLICTS.md", "CHANGELOG.md"):
            continue

        content = md_file.read_text()
        # Check if the existing article mentions the filed article's title
        if filed_title.lower() in content.lower() and f"[[{filed_slug}]]" not in content:
            # Add to Referenced By section if it exists, otherwise append
            if "## Referenced By" in content:
                content = content.replace(
                    "## Referenced By",
                    f"## Referenced By\n- [[{filed_slug}]]",
                )
            else:
                content += f"\n\n## Referenced By\n- [[{filed_slug}]]\n"
            md_file.write_text(content)
            backlinks_added += 1

    return backlinks_added


def file_to_wiki(
    report_path: Path,
    wfs: WikiFileSystem,
) -> dict:
    """File a Q&A output (report or slides) into the wiki.

    Returns:
        Dict with: filed_path, category, backlinks_added, status
    """
    if not report_path.exists():
        return {"status": "error", "message": f"File not found: {report_path}"}

    post = frontmatter.load(str(report_path))
    title = post.metadata.get("title", report_path.stem)
    content = post.content

    # Check content hash for duplicate
    c_hash = text_hash(content)
    for md_file in wfs.wiki_dir.rglob("*.md"):
        if any(p.startswith(".") for p in md_file.relative_to(wfs.wiki_dir).parts):
            continue
        try:
            existing = frontmatter.load(str(md_file))
            if existing.metadata.get("content_hash") == c_hash:
                return {
                    "status": "duplicate",
                    "message": f"Identical content already exists: {md_file.name}",
                    "existing": str(md_file),
                }
        except Exception:
            continue

    # Check for similar article
    similar = _find_similar_article(title, wfs.wiki_dir)
    if similar:
        return {
            "status": "similar",
            "message": f"Similar article exists: {similar.name}",
            "similar_path": str(similar),
        }

    # Detect category
    concepts_path = wfs.wiki_dir / "CONCEPTS.md"
    category = _detect_category(content, concepts_path)

    # Update frontmatter for wiki
    post.metadata["origin"] = "qa-output"
    post.metadata["filed_at"] = datetime.now(UTC).isoformat()
    post.metadata["content_hash"] = c_hash
    post.metadata["category"] = category
    post.metadata["status"] = "published"
    if "filed_to_wiki" in post.metadata:
        post.metadata["filed_to_wiki"] = True

    # Write to wiki
    category_dir = wfs.wiki_dir / category
    category_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w\s-]", "", title.lower()[:80])
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    filed_path = category_dir / f"{slug}.md"

    counter = 2
    while filed_path.exists():
        filed_path = category_dir / f"{slug}-{counter}.md"
        counter += 1

    filed_path.write_text(frontmatter.dumps(post))

    # Insert backlinks
    backlinks_added = _insert_backlinks(filed_path, wfs.wiki_dir)

    # Update INDEX.md
    index_path = wfs.wiki_dir / "INDEX.md"
    if index_path.exists():
        index_content = index_path.read_text()
        summary = content.strip().split("\n")[0][:100] if content.strip() else ""
        new_entry = f"| [[{slug}|{title}]] | {category} | {summary} |\n"
        # Insert before the last line
        index_content = index_content.rstrip() + "\n" + new_entry
        index_path.write_text(index_content)

    # Append to log.md
    log_path = wfs.wiki_dir / "log.md"
    from compendium.pipeline.steps import build_log_entry

    log_entry = build_log_entry("file to wiki", notes=f"Filed '{title}' to {category}/")
    from compendium.pipeline.controller import _append_log

    _append_log(log_path, log_entry)

    return {
        "status": "filed",
        "filed_path": str(filed_path),
        "category": category,
        "backlinks_added": backlinks_added,
    }

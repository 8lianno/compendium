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
    resolution: str | None = None,
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
    if similar and resolution not in {"replace", "merge", "keep_both"}:
        return {
            "status": "similar",
            "message": f"Similar article exists: {similar.name}",
            "similar_path": str(similar),
        }
    if resolution == "cancel":
        return {"status": "cancelled", "message": "Filing cancelled"}

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
    existing_path = similar if similar and similar.exists() else category_dir / f"{slug}.md"
    action = resolution or "keep_both"

    if action == "replace" and existing_path.exists():
        filed_path = existing_path
        post.metadata["updated_at"] = datetime.now(UTC).isoformat()
        filed_path.write_text(frontmatter.dumps(post))
    elif action == "merge" and existing_path.exists():
        existing_post = frontmatter.load(str(existing_path))
        merged_body = existing_post.content.rstrip()
        merged_body += f"\n\n## QA Output Merge\n\n{content.strip()}\n"
        existing_post.content = merged_body
        existing_post.metadata["updated_at"] = datetime.now(UTC).isoformat()
        existing_post.metadata["origin"] = existing_post.metadata.get("origin", "qa-output")
        existing_post.metadata["content_hash"] = text_hash(existing_post.content)
        filed_path = existing_path
        filed_path.write_text(frontmatter.dumps(existing_post))
    else:
        filed_path = category_dir / f"{slug}.md"
        counter = 2
        while filed_path.exists():
            filed_path = category_dir / f"{slug}-{counter}.md"
            counter += 1
        filed_path.write_text(frontmatter.dumps(post))
        action = "keep_both"

    # Insert backlinks
    backlinks_added = _insert_backlinks(filed_path, wfs.wiki_dir)

    from compendium.pipeline.index_ops import rebuild_wiki_index

    rebuild_wiki_index(wfs.wiki_dir)
    wfs.refresh_search_index()

    # Append to log.md
    from compendium.pipeline.steps import build_log_entry

    log_entry = build_log_entry(
        "file",
        title=title[:80],
        notes=f"Action: {action}; category: {category}; backlinks added: {backlinks_added}",
    )
    wfs.append_log_entry(log_entry)
    wfs.auto_commit(
        f"[file]: {title[:72]}",
        paths=[filed_path, wfs.wiki_dir / "INDEX.md", wfs.wiki_dir / "log.md"],
    )

    return {
        "status": "filed",
        "filed_path": str(filed_path),
        "category": category,
        "backlinks_added": backlinks_added,
        "action": action,
    }

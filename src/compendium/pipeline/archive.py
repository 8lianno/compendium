"""Archive and restore operations for source management.

Source-agnostic: works for any raw/ source, not just Apple Books.
Moves files between active (raw/, wiki/) and archive (archive/sources/, archive/wiki/)
while keeping the dependency graph consistent.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import frontmatter

if TYPE_CHECKING:
    from pathlib import Path

    from compendium.core.wiki_fs import WikiFileSystem


@dataclass
class ArchiveResult:
    """Result of an archive or restore operation."""

    sources_moved: list[str] = field(default_factory=list)
    articles_archived: list[str] = field(default_factory=list)
    articles_restored: list[str] = field(default_factory=list)
    articles_patched: list[str] = field(default_factory=list)
    index_rebuilt: bool = False


def archive_source(
    wfs: WikiFileSystem,
    source_rel_path: str,
) -> ArchiveResult:
    """Archive a source and cascade effects to dependent wiki articles.

    Moves raw/{file} → archive/sources/{file}.
    Articles that depend ONLY on this source are moved to archive/wiki/.
    Articles with multiple sources get the archived source ref removed from frontmatter.
    Dependency graph is updated. Index is rebuilt.

    Args:
        wfs: WikiFileSystem instance
        source_rel_path: Relative path like "raw/deep-work-highlights.md"
    """
    from compendium.pipeline.deps import DependencyGraph
    from compendium.pipeline.index_ops import rebuild_wiki_index

    result = ArchiveResult()
    source_full = wfs.root / source_rel_path

    if not source_full.exists():
        return result

    # 1. Move source to archive
    dest = wfs.archive_sources_dir / source_full.name
    wfs.archive_sources_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_full), str(dest))
    result.sources_moved.append(source_rel_path)

    # 2. Load dependency graph
    deps = DependencyGraph.load(wfs.deps_path)
    affected = deps.get_affected_articles([source_rel_path])

    # 3. Handle affected articles
    for article_rel in affected:
        article_entry = deps.articles.get(article_rel)
        if not article_entry:
            continue

        active_deps = [
            d for d in article_entry.depends_on
            if d != source_rel_path and d not in deps.archived_sources
        ]

        article_full = wfs.root / article_rel
        if not article_full.exists():
            continue

        if not active_deps:
            # Article depends ONLY on this source → archive the article
            archive_dest = wfs.archive_wiki_dir / article_full.relative_to(wfs.wiki_dir)
            archive_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(article_full), str(archive_dest))
            result.articles_archived.append(article_rel)
        else:
            # Article has other active sources → remove archived source ref from frontmatter
            _remove_source_ref(article_full, source_rel_path)
            result.articles_patched.append(article_rel)

    # 4. Update dependency graph
    source_entry = deps.sources.pop(source_rel_path, None)
    if source_entry:
        deps.archived_sources[source_rel_path] = source_entry

    # Remove archived articles from deps
    for article_rel in result.articles_archived:
        deps.articles.pop(article_rel, None)

    deps.update_meta()
    deps.save(wfs.deps_path)

    # 5. Rebuild index
    if wfs.wiki_dir.exists():
        rebuild_wiki_index(wfs.wiki_dir)
        result.index_rebuilt = True

    return result


def restore_source(
    wfs: WikiFileSystem,
    source_rel_path: str,
) -> ArchiveResult:
    """Restore a previously archived source and its dependent articles.

    Moves archive/sources/{file} → raw/{file}.
    Restores archived articles that depended on this source back to wiki/.
    No re-summarization needed — original compiled articles are preserved.

    Args:
        wfs: WikiFileSystem instance
        source_rel_path: Relative path like "raw/deep-work-highlights.md"
    """
    from compendium.pipeline.deps import DependencyGraph
    from compendium.pipeline.index_ops import rebuild_wiki_index

    result = ArchiveResult()

    # Derive the filename from the rel path
    from pathlib import PurePosixPath

    source_name = PurePosixPath(source_rel_path).name
    archived_source = wfs.archive_sources_dir / source_name
    restore_dest = wfs.root / source_rel_path

    if not archived_source.exists():
        return result

    # 1. Move source back to raw/
    restore_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(archived_source), str(restore_dest))
    result.sources_moved.append(source_rel_path)

    # 2. Load dependency graph
    deps = DependencyGraph.load(wfs.deps_path)

    # 3. Restore the source entry in deps
    source_entry = deps.archived_sources.pop(source_rel_path, None)
    if source_entry:
        deps.sources[source_rel_path] = source_entry

        # 4. Restore archived articles that depended on this source
        for article_rel in source_entry.produces:
            # Check if the article is in archive/wiki/
            article_pp = PurePosixPath(article_rel)
            article_name = (
                article_pp.relative_to("wiki") if "wiki" in article_rel else article_pp
            )
            archived_article = wfs.archive_wiki_dir / str(article_name)
            if not archived_article.exists():
                # Try just the filename
                archived_article = wfs.archive_wiki_dir / article_pp.name
            if not archived_article.exists():
                continue

            restore_article_dest = wfs.root / article_rel
            restore_article_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archived_article), str(restore_article_dest))
            result.articles_restored.append(article_rel)

    deps.update_meta()
    deps.save(wfs.deps_path)

    # 5. Rebuild index
    if wfs.wiki_dir.exists():
        rebuild_wiki_index(wfs.wiki_dir)
        result.index_rebuilt = True

    return result


def _remove_source_ref(article_path: Path, source_rel_path: str) -> None:
    """Remove a source reference from an article's frontmatter."""
    try:
        post = frontmatter.load(str(article_path))
        sources = post.metadata.get("sources", [])
        updated = [s for s in sources if _source_ref_str(s) != source_rel_path]
        post.metadata["sources"] = updated
        article_path.write_text(frontmatter.dumps(post))
    except Exception:
        pass


def _source_ref_str(source_ref: object) -> str:
    """Extract the ref string from a source reference (dict or string)."""
    if isinstance(source_ref, dict):
        return source_ref.get("ref", "")
    return str(source_ref)

"""Download remote images in wiki articles for offline access."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from pathlib import Path

# Matches ![alt text](https://...) but not ![alt](local/path.png)
REMOTE_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")


def scan_remote_images(wiki_dir: Path) -> list[tuple[Path, list[str]]]:
    """Scan wiki articles for remote image URLs.

    Returns list of (article_path, [url, ...]) tuples.
    """
    results: list[tuple[Path, list[str]]] = []
    for md_file in sorted(wiki_dir.rglob("*.md")):
        # Skip structural/hidden files
        rel = md_file.relative_to(wiki_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            text = md_file.read_text(errors="replace")
        except OSError:
            continue
        urls = REMOTE_IMAGE_PATTERN.findall(text)
        if urls:
            results.append((md_file, [url for _, url in urls]))
    return results


def _guess_extension(url: str, content_type: str | None) -> str:
    """Guess file extension from URL or content-type header."""
    from pathlib import PurePosixPath

    # Try URL path first
    url_path = PurePosixPath(url.split("?")[0].split("#")[0])
    if url_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return url_path.suffix.lower()

    # Try content-type
    if content_type:
        ct = content_type.lower()
        if "png" in ct:
            return ".png"
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        if "gif" in ct:
            return ".gif"
        if "webp" in ct:
            return ".webp"
        if "svg" in ct:
            return ".svg"

    return ".png"  # default


def download_and_localize(
    article_path: Path,
    images_dir: Path,
    *,
    timeout: float = 30.0,
) -> tuple[int, int]:
    """Download remote images in an article and replace URLs with local paths.

    Returns (downloaded_count, failed_count).
    """
    text = article_path.read_text(errors="replace")
    matches = list(REMOTE_IMAGE_PATTERN.finditer(text))
    if not matches:
        return 0, 0

    # Create per-article image directory
    slug = article_path.stem
    article_images_dir = images_dir / slug
    article_images_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    new_text = text

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for i, match in enumerate(matches, 1):
            alt_text = match.group(1)
            url = match.group(2)

            try:
                resp = client.get(url)
                resp.raise_for_status()
            except (httpx.HTTPError, OSError):
                failed += 1
                continue

            ext = _guess_extension(url, resp.headers.get("content-type"))
            local_name = f"img_{i}{ext}"
            local_path = article_images_dir / local_name
            local_path.write_bytes(resp.content)

            # Compute relative path from article to image
            try:
                rel_path = local_path.relative_to(article_path.parent)
            except ValueError:
                # Different trees — use path from wiki root
                rel_path = local_path

            old_ref = f"![{alt_text}]({url})"
            new_ref = f"![{alt_text}]({rel_path})"
            new_text = new_text.replace(old_ref, new_ref, 1)
            downloaded += 1

    if downloaded > 0:
        article_path.write_text(new_text)

    return downloaded, failed

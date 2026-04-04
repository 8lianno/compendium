"""Web article clipping — HTML to clean markdown with local images."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter
import httpx
from markdownify import markdownify as md
from readability import Document

from compendium.ingest.dedup import find_duplicate_by_url, text_hash

if TYPE_CHECKING:
    from pathlib import Path


def slugify(text: str, max_len: int = 80) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len]


async def download_image(url: str, dest: Path, client: httpx.AsyncClient) -> bool:
    """Download an image to local path. Returns True on success."""
    try:
        response = await client.get(url, follow_redirects=True, timeout=15.0)
        response.raise_for_status()
        # Skip files > 20MB
        if len(response.content) > 20 * 1024 * 1024:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(response.content)
        return True
    except Exception:
        return False


def _extract_image_urls(html: str) -> list[str]:
    """Extract all image src URLs from HTML."""
    return re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)


def _guess_extension(url: str) -> str:
    """Guess image extension from URL."""
    url_lower = url.lower().split("?")[0]
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        if url_lower.endswith(ext):
            return ext
    return ".png"  # default


def _extract_meta(name: str, html: str) -> str:
    """Extract a meta tag value by name/property."""
    patterns = [
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _extract_language(html: str) -> str:
    match = re.search(r"<html[^>]+lang=[\"']([^\"']+)[\"']", html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


async def clip_webpage(
    url: str,
    html: str,
    raw_dir: Path,
    images_dir: Path,
    duplicate_mode: str = "cancel",
) -> tuple[Path | None, str]:
    """Clip a webpage to markdown with local images.

    Args:
        url: The source URL
        html: Raw HTML content of the page
        raw_dir: Directory to save the markdown file
        images_dir: Directory to save downloaded images

    Returns:
        Tuple of (output_path, status_message).
        output_path is None if clipping failed.
    """
    # Check for duplicates
    existing = find_duplicate_by_url(raw_dir, url)
    if existing and duplicate_mode == "cancel":
        return None, f"duplicate:{existing.name}"
    overwrite_existing = existing if existing and duplicate_mode == "overwrite" else None

    # Extract article content using Readability
    doc = Document(html)
    title = doc.title()
    article_html = doc.summary()
    author = _extract_meta("author", html) or _extract_meta("article:author", html)
    language = _extract_language(html)
    partial = False
    plain_text = re.sub(r"<[^>]+>", " ", html).strip()

    if (not plain_text or len(plain_text) < 5) and (not article_html or len(article_html) < 200):
        return None, "no_content"

    # Convert HTML to markdown
    markdown_content = ""
    clip_format = "markdown"
    if article_html and len(article_html.strip()) >= 50:
        markdown_content = md(
            article_html,
            heading_style="ATX",
            code_language_callback=lambda el: (
                el.get("class", [""])[0].replace("language-", "") if el.get("class") else ""
            ),
            strip=["script", "style"],
        )

    if not markdown_content or not markdown_content.strip():
        partial = True
        clip_format = "html-raw"
        markdown_content = (
            f"# {title or 'Clipped Page'}\n\n"
            "## Raw HTML Fallback\n\n"
            "```html\n"
            f"{html[:50000]}\n"
            "```\n"
        )

    # Download images
    slug = slugify(title)
    img_dir = images_dir / slug
    image_urls = _extract_image_urls(article_html)
    downloaded = 0
    failed = 0

    async with httpx.AsyncClient() as client:
        for i, img_url in enumerate(image_urls):
            # Resolve relative URLs
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                from urllib.parse import urlparse

                parsed = urlparse(url)
                img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
            elif not img_url.startswith("http"):
                continue  # Skip data URIs, etc.

            ext = _guess_extension(img_url)
            img_name = f"img_{i + 1}{ext}"
            img_path = img_dir / img_name

            if await download_image(img_url, img_path, client):
                # Replace URL in markdown with local path
                rel_path = f"images/{slug}/{img_name}"
                markdown_content = markdown_content.replace(img_url, rel_path)
                downloaded += 1
            else:
                # Mark failed downloads
                markdown_content = markdown_content.replace(
                    img_url,
                    f"{img_url} <!-- [REMOTE: download failed] -->",
                )
                failed += 1

    word_count = len(markdown_content.split())

    # Build frontmatter
    fm_data = {
        "title": title,
        "id": slug,
        "source_url": url,
        "source": "web-clip",
        "format": clip_format,
        "clipped_at": datetime.now(UTC).isoformat(),
        "word_count": word_count,
        "content_hash": text_hash(markdown_content),
        "status": "raw",
        "author": author,
        "language": language,
        "partial": partial,
    }

    # Save markdown file
    post = frontmatter.Post(markdown_content, **fm_data)
    output_path = overwrite_existing or raw_dir / f"{slug}.md"

    if overwrite_existing is None:
        counter = 2
        while output_path.exists():
            output_path = raw_dir / f"{slug}-{counter}.md"
            counter += 1

    output_path.write_text(frontmatter.dumps(post))
    from compendium.core.wiki_fs import WikiFileSystem

    WikiFileSystem(raw_dir.parent).append_clip_log(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "url": url,
            "title": title,
            "path": str(output_path.relative_to(raw_dir.parent)),
            "duplicate_mode": duplicate_mode,
            "format": clip_format,
            "partial": partial,
            "images_downloaded": downloaded,
            "images_failed": failed,
        }
    )

    # Build status message
    img_msg = ""
    if downloaded > 0 or failed > 0:
        img_msg = f" ({downloaded} images"
        if failed > 0:
            img_msg += f", {failed} failed"
        img_msg += ")"

    fallback_msg = " [raw HTML fallback]" if partial else ""
    return output_path, f"Clipped: {title} ({word_count:,} words){img_msg}{fallback_msg}"

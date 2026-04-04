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


async def clip_webpage(
    url: str,
    html: str,
    raw_dir: Path,
    images_dir: Path,
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
    if existing:
        return None, f"duplicate:{existing.name}"

    # Extract article content using Readability
    doc = Document(html)
    title = doc.title()
    article_html = doc.summary()

    if not article_html or len(article_html.strip()) < 50:
        return None, "no_content"

    # Convert HTML to markdown
    markdown_content = md(
        article_html,
        heading_style="ATX",
        code_language_callback=lambda el: (
            el.get("class", [""])[0].replace("language-", "") if el.get("class") else ""
        ),
        strip=["script", "style"],
    )

    if not markdown_content or not markdown_content.strip():
        return None, "no_content"

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
        "format": "markdown",
        "clipped_at": datetime.now(UTC).isoformat(),
        "word_count": word_count,
        "content_hash": text_hash(markdown_content),
        "status": "raw",
    }

    # Save markdown file
    post = frontmatter.Post(markdown_content, **fm_data)
    output_path = raw_dir / f"{slug}.md"

    counter = 2
    while output_path.exists():
        output_path = raw_dir / f"{slug}-{counter}.md"
        counter += 1

    output_path.write_text(frontmatter.dumps(post))

    # Build status message
    img_msg = ""
    if downloaded > 0 or failed > 0:
        img_msg = f" ({downloaded} images"
        if failed > 0:
            img_msg += f", {failed} failed"
        img_msg += ")"

    return output_path, f"Clipped: {title} ({word_count:,} words){img_msg}"

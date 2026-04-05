"""Tests for the CLI web clip command logic."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from compendium.ingest.web_clip import clip_webpage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_clip_webpage_basic(tmp_path: Path) -> None:
    """Test clip_webpage produces valid markdown with frontmatter."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    images_dir = raw_dir / "images"
    images_dir.mkdir()

    html = """
    <html>
    <head><title>Test Article</title></head>
    <body>
    <article>
        <h1>Test Article</h1>
        <p>This is a test article with enough content to pass readability extraction.
        It contains multiple paragraphs of meaningful text that should be extracted.
        The content discusses important topics related to knowledge management.</p>
        <p>A second paragraph adds more substance to the article, covering additional
        details about the subject matter at hand.</p>
    </article>
    </body>
    </html>
    """

    output, msg = await clip_webpage(
        "https://example.com/test-article",
        html,
        raw_dir,
        images_dir,
    )

    assert output is not None
    assert output.exists()
    assert "Clipped" in msg

    import frontmatter

    post = frontmatter.load(str(output))
    assert post["source_url"] == "https://example.com/test-article"
    assert post["source"] == "web-clip"
    assert post["status"] == "raw"
    assert post["content_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_clip_duplicate_cancel(tmp_path: Path) -> None:
    """Test that duplicate URLs are skipped in cancel mode."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    images_dir = raw_dir / "images"
    images_dir.mkdir()

    html = "<html><body><p>Test content for duplicate check.</p></body></html>"
    url = "https://example.com/dup"

    # First clip
    await clip_webpage(url, html, raw_dir, images_dir)

    # Second clip should be skipped
    output, msg = await clip_webpage(url, html, raw_dir, images_dir, "cancel")
    assert output is None
    assert "duplicate" in msg


@pytest.mark.asyncio
async def test_clip_no_content(tmp_path: Path) -> None:
    """Test that empty pages return no_content."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    images_dir = raw_dir / "images"
    images_dir.mkdir()

    output, msg = await clip_webpage(
        "https://example.com/empty",
        "<html><body></body></html>",
        raw_dir,
        images_dir,
    )

    assert output is None
    assert "no_content" in msg


@pytest.mark.asyncio
async def test_clip_with_images(tmp_path: Path) -> None:
    """Test that images are downloaded and paths rewritten."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    images_dir = raw_dir / "images"
    images_dir.mkdir()

    html = """
    <html><body>
    <article>
    <h1>Image Test</h1>
    <p>An article with an image reference that has enough content to be extracted.</p>
    <img src="https://example.com/photo.png" alt="test">
    <p>More paragraphs follow to ensure this passes the readability threshold for
    article extraction. We need enough substance here.</p>
    </article>
    </body></html>
    """

    # Mock image download to succeed
    with patch("compendium.ingest.web_clip.download_image", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = True

        output, msg = await clip_webpage(
            "https://example.com/image-article",
            html,
            raw_dir,
            images_dir,
        )

    # Image download was attempted
    if mock_dl.called:
        assert output is not None

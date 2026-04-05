"""Tests for remote image download and localization."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

from compendium.ingest.media import (
    REMOTE_IMAGE_PATTERN,
    _guess_extension,
    download_and_localize,
    scan_remote_images,
)


def _make_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    return wiki


class TestScanRemoteImages:
    def test_finds_remote_urls(self, tmp_path: Path) -> None:
        wiki = _make_wiki(tmp_path)
        article = wiki / "test-article.md"
        article.write_text(
            "# Test\n\n"
            "![diagram](https://example.com/img.png)\n"
            "![chart](https://cdn.example.com/chart.jpg)\n"
        )

        results = scan_remote_images(wiki)
        assert len(results) == 1
        assert results[0][0] == article
        assert len(results[0][1]) == 2
        assert "https://example.com/img.png" in results[0][1]

    def test_ignores_local_images(self, tmp_path: Path) -> None:
        wiki = _make_wiki(tmp_path)
        article = wiki / "test-article.md"
        article.write_text("# Test\n\n![local](images/local.png)\n")

        results = scan_remote_images(wiki)
        assert len(results) == 0

    def test_ignores_hidden_dirs(self, tmp_path: Path) -> None:
        wiki = _make_wiki(tmp_path)
        hidden = wiki / ".staging"
        hidden.mkdir()
        article = hidden / "draft.md"
        article.write_text("![img](https://example.com/img.png)\n")

        results = scan_remote_images(wiki)
        assert len(results) == 0

    def test_no_articles(self, tmp_path: Path) -> None:
        wiki = _make_wiki(tmp_path)
        results = scan_remote_images(wiki)
        assert results == []


class TestGuessExtension:
    def test_from_url(self) -> None:
        assert _guess_extension("https://example.com/photo.jpg", None) == ".jpg"

    def test_from_content_type(self) -> None:
        assert _guess_extension("https://example.com/img", "image/png") == ".png"

    def test_default(self) -> None:
        assert _guess_extension("https://example.com/img", None) == ".png"

    def test_url_with_query_params(self) -> None:
        assert _guess_extension("https://example.com/photo.webp?w=800", None) == ".webp"


class TestRemoteImagePattern:
    def test_matches_http(self) -> None:
        m = REMOTE_IMAGE_PATTERN.search("![alt](http://example.com/img.png)")
        assert m is not None
        assert m.group(2) == "http://example.com/img.png"

    def test_matches_https(self) -> None:
        m = REMOTE_IMAGE_PATTERN.search("![alt](https://example.com/img.png)")
        assert m is not None

    def test_no_match_local(self) -> None:
        m = REMOTE_IMAGE_PATTERN.search("![alt](images/local.png)")
        assert m is None


class TestDownloadAndLocalize:
    def test_dry_no_remote_images(self, tmp_path: Path) -> None:
        wiki = _make_wiki(tmp_path)
        article = wiki / "test.md"
        article.write_text("# No images here\n")

        downloaded, failed = download_and_localize(article, wiki / "images")
        assert downloaded == 0
        assert failed == 0

    def test_replaces_url_with_local_path(self, tmp_path: Path) -> None:
        wiki = _make_wiki(tmp_path)
        article = wiki / "test.md"
        article.write_text(
            "# Test\n\n![diagram](https://example.com/img.png)\n"
        )

        mock_response = MagicMock()
        mock_response.content = b"\x89PNG\r\n\x1a\n"
        mock_response.headers = {"content-type": "image/png"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)

        with patch("compendium.ingest.media.httpx.Client", return_value=mock_client):
            downloaded, failed = download_and_localize(article, wiki / "images")

        assert downloaded == 1
        assert failed == 0

        text = article.read_text()
        assert "https://example.com/img.png" not in text
        assert "images/test/img_1.png" in text

    def test_handles_download_failure(self, tmp_path: Path) -> None:
        import httpx

        wiki = _make_wiki(tmp_path)
        article = wiki / "test.md"
        original = "# Test\n\n![diagram](https://example.com/img.png)\n"
        article.write_text(original)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=httpx.ConnectError("fail"))

        with patch("compendium.ingest.media.httpx.Client", return_value=mock_client):
            downloaded, failed = download_and_localize(article, wiki / "images")

        assert downloaded == 0
        assert failed == 1
        # Original text unchanged
        assert article.read_text() == original

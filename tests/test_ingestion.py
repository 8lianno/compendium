"""Tests for source ingestion — file drop, web clip, PDF, dedup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frontmatter
import pytest

from compendium.ingest.dedup import content_hash, find_duplicate_by_hash, find_duplicate_by_url
from compendium.ingest.file_drop import (
    ingest_batch,
    ingest_file,
    slugify,
)

if TYPE_CHECKING:
    from pathlib import Path

FIXTURES_DIR = __import__("pathlib").Path(__file__).parent / "fixtures"


# -- Fixtures --


@pytest.fixture
def raw_project(tmp_path: Path) -> dict[str, Path]:
    """Create a project directory structure for testing."""
    raw_dir = tmp_path / "raw"
    images_dir = tmp_path / "raw" / "images"
    originals_dir = tmp_path / "raw" / "originals"
    raw_dir.mkdir(parents=True)
    images_dir.mkdir(parents=True)
    originals_dir.mkdir(parents=True)
    return {
        "root": tmp_path,
        "raw": raw_dir,
        "images": images_dir,
        "originals": originals_dir,
    }


# -- Slugify --


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert slugify("Test: A Paper (2024)") == "test-a-paper-2024"

    def test_max_length(self) -> None:
        long = "a" * 200
        assert len(slugify(long)) == 80

    def test_unicode(self) -> None:
        result = slugify("Über die Grundlagen")
        assert "ber-die-grundlagen" in result


# -- Dedup --


class TestDedup:
    def test_content_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h = content_hash(f)
        assert h.startswith("sha256:")
        assert content_hash(f) == h  # Deterministic

    def test_find_duplicate_by_url(self, raw_project: dict[str, Path]) -> None:
        raw_dir = raw_project["raw"]
        # Create a source with a URL
        post = frontmatter.Post("Content", source_url="https://example.com/article")
        (raw_dir / "test.md").write_text(frontmatter.dumps(post))

        assert find_duplicate_by_url(raw_dir, "https://example.com/article") is not None
        assert find_duplicate_by_url(raw_dir, "https://other.com") is None

    def test_find_duplicate_by_hash(self, raw_project: dict[str, Path]) -> None:
        raw_dir = raw_project["raw"]
        post = frontmatter.Post("Content", content_hash="sha256:abc123")
        (raw_dir / "test.md").write_text(frontmatter.dumps(post))

        assert find_duplicate_by_hash(raw_dir, "sha256:abc123") is not None
        assert find_duplicate_by_hash(raw_dir, "sha256:different") is None

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert find_duplicate_by_url(tmp_path / "nonexistent", "url") is None
        assert find_duplicate_by_hash(tmp_path / "nonexistent", "hash") is None


# -- Markdown Ingestion --


class TestMarkdownIngestion:
    def test_ingest_md_file(self, raw_project: dict[str, Path]) -> None:
        # Create a test markdown file
        src = raw_project["root"] / "test-article.md"
        src.write_text("# Test Article\n\nSome content here.")

        result = ingest_file(
            src, raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert result.success
        assert result.output_path is not None
        assert result.output_path.exists()

        # Verify frontmatter
        post = frontmatter.load(str(result.output_path))
        assert post.metadata["format"] == "markdown"
        assert post.metadata["source"] == "local"
        assert post.metadata["status"] == "raw"
        assert post.metadata["word_count"] > 0

    def test_ingest_md_with_existing_frontmatter(self, raw_project: dict[str, Path]) -> None:
        src = raw_project["root"] / "with-fm.md"
        src.write_text("---\ntitle: My Custom Title\nauthor: Test Author\n---\n\nBody text.")

        result = ingest_file(
            src, raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert result.success
        post = frontmatter.load(str(result.output_path))
        assert post.metadata["title"] == "My Custom Title"
        assert post.metadata["author"] == "Test Author"
        assert post.metadata["source"] == "local"

    def test_ingest_txt_file(self, raw_project: dict[str, Path]) -> None:
        src = raw_project["root"] / "notes.txt"
        src.write_text("Plain text notes about something.")

        result = ingest_file(
            src, raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert result.success
        assert result.output_path is not None
        assert result.output_path.suffix == ".md"


# -- CSV Ingestion --


class TestCSVIngestion:
    def test_ingest_csv(self, raw_project: dict[str, Path]) -> None:
        src = raw_project["root"] / "data.csv"
        src.write_text("name,value,score\nAlice,100,0.95\nBob,200,0.87\n")

        result = ingest_file(
            src, raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert result.success
        post = frontmatter.load(str(result.output_path))
        assert post.metadata["format"] == "csv"
        assert post.metadata["row_count"] == 2
        assert "name" in post.metadata["columns"]


# -- Image Ingestion --


class TestImageIngestion:
    def test_ingest_image(self, raw_project: dict[str, Path]) -> None:
        # Create a fake PNG file
        src = raw_project["root"] / "diagram.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        result = ingest_file(
            src, raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert result.success
        assert result.output_path is not None
        assert "standalone" in str(result.output_path)


# -- Unsupported Files --


class TestUnsupported:
    def test_unsupported_extension(self, raw_project: dict[str, Path]) -> None:
        src = raw_project["root"] / "video.mp4"
        src.write_bytes(b"\x00" * 100)

        result = ingest_file(
            src, raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert not result.success
        assert "Unsupported" in result.message

    def test_nonexistent_file(self, raw_project: dict[str, Path]) -> None:
        result = ingest_file(
            raw_project["root"] / "nonexistent.md",
            raw_project["raw"],
            raw_project["images"],
            raw_project["originals"],
        )
        assert not result.success
        assert "not found" in result.message


# -- Batch Ingestion --


class TestBatchIngestion:
    def test_batch_mixed_files(self, raw_project: dict[str, Path]) -> None:
        # Create several files
        (raw_project["root"] / "doc1.md").write_text("# Doc 1\nContent")
        (raw_project["root"] / "doc2.txt").write_text("Plain text")
        (raw_project["root"] / "data.csv").write_text("a,b\n1,2\n")
        (raw_project["root"] / "bad.mp4").write_bytes(b"\x00")

        paths = [
            raw_project["root"] / "doc1.md",
            raw_project["root"] / "doc2.txt",
            raw_project["root"] / "data.csv",
            raw_project["root"] / "bad.mp4",
        ]

        result = ingest_batch(
            paths, raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert result.succeeded == 3
        assert result.failed == 1
        assert result.total == 4

    def test_batch_directory(self, raw_project: dict[str, Path]) -> None:
        subdir = raw_project["root"] / "sources"
        subdir.mkdir()
        (subdir / "a.md").write_text("# A")
        (subdir / "b.md").write_text("# B")
        (subdir / "c.txt").write_text("C")

        result = ingest_batch(
            [subdir], raw_project["raw"], raw_project["images"], raw_project["originals"]
        )
        assert result.succeeded == 3

    def test_dedup_prevents_reingest(self, raw_project: dict[str, Path]) -> None:
        src = raw_project["root"] / "doc.md"
        src.write_text("# Same Content")

        r1 = ingest_file(src, raw_project["raw"], raw_project["images"], raw_project["originals"])
        assert r1.success

        r2 = ingest_file(src, raw_project["raw"], raw_project["images"], raw_project["originals"])
        assert not r2.success
        assert "Duplicate" in r2.message


# -- PDF Ingestion --


class TestPDFIngestion:
    def test_pdf_extraction(self, raw_project: dict[str, Path]) -> None:
        """Test PDF extraction using a fixture or skip if no fixture available."""
        # Create a minimal PDF using PyMuPDF
        import pymupdf

        from compendium.ingest.pdf import extract_pdf

        pdf_path = raw_project["root"] / "test.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Test PDF Content\n\nThis is a test document.")
        doc.save(str(pdf_path))
        doc.close()

        output = extract_pdf(
            pdf_path,
            raw_project["raw"],
            raw_project["originals"],
            raw_project["images"],
        )

        assert output.exists()
        post = frontmatter.load(str(output))
        assert post.metadata["format"] == "pdf-extracted"
        assert post.metadata["page_count"] == 1
        assert post.metadata["source"] == "local"
        assert "Test PDF Content" in post.content

        # Original should be preserved
        assert (raw_project["originals"] / "test.pdf").exists()


# -- Web Clip --


class TestWebClip:
    @pytest.mark.asyncio
    async def test_clip_basic_html(self, raw_project: dict[str, Path]) -> None:
        from compendium.ingest.web_clip import clip_webpage

        html = """
        <html>
        <head><title>Test Article</title></head>
        <body>
            <article>
                <h1>Test Article</h1>
                <p>This is a test article with enough content to pass the readability
                threshold. We need several sentences to make readability happy. Let's add
                more text here to ensure extraction works properly. The article discusses
                important topics about knowledge management and research synthesis.</p>
                <p>Another paragraph with more content about the topic. This helps ensure
                that the readability algorithm considers this a real article and not just
                boilerplate navigation or footer content.</p>
            </article>
        </body>
        </html>
        """

        output_path, message = await clip_webpage(
            url="https://example.com/test-article",
            html=html,
            raw_dir=raw_project["raw"],
            images_dir=raw_project["images"],
        )

        assert output_path is not None
        assert output_path.exists()
        assert "Clipped:" in message

        post = frontmatter.load(str(output_path))
        assert post.metadata["source"] == "web-clip"
        assert post.metadata["source_url"] == "https://example.com/test-article"
        assert post.metadata["format"] == "markdown"
        assert post.metadata["word_count"] > 0

    @pytest.mark.asyncio
    async def test_clip_duplicate_url(self, raw_project: dict[str, Path]) -> None:
        from compendium.ingest.web_clip import clip_webpage

        # Pre-create a source with the same URL
        post = frontmatter.Post("Existing", source_url="https://example.com/dup")
        (raw_project["raw"] / "existing.md").write_text(frontmatter.dumps(post))

        output_path, message = await clip_webpage(
            url="https://example.com/dup",
            html="<html><body><p>Content</p></body></html>",
            raw_dir=raw_project["raw"],
            images_dir=raw_project["images"],
        )

        assert output_path is None
        assert "duplicate" in message

    @pytest.mark.asyncio
    async def test_clip_empty_content(self, raw_project: dict[str, Path]) -> None:
        from compendium.ingest.web_clip import clip_webpage

        output_path, message = await clip_webpage(
            url="https://example.com/empty",
            html="<html><body></body></html>",
            raw_dir=raw_project["raw"],
            images_dir=raw_project["images"],
        )

        assert output_path is None
        assert message == "no_content"

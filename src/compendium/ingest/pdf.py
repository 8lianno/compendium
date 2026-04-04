"""PDF to markdown extraction using PyMuPDF."""

from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter

from compendium.ingest.dedup import content_hash

if TYPE_CHECKING:
    from pathlib import Path


def slugify(text: str, max_len: int = 80) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len]


def extract_pdf(
    pdf_path: Path,
    raw_dir: Path,
    originals_dir: Path,
    images_dir: Path,
) -> Path:
    """Extract text and images from a PDF, save as markdown in raw/.

    Returns the path to the generated markdown file.
    """
    import pymupdf  # type: ignore[import-untyped]

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as exc:
        message = str(exc).lower()
        if "password" in message or "encrypted" in message:
            raise ValueError("Password-protected PDF") from exc
        raise ValueError("Corrupt or unreadable PDF") from exc

    # Extract metadata
    meta = doc.metadata or {}
    title = meta.get("title", "") or pdf_path.stem
    author = meta.get("author", "")
    page_count = len(doc)

    # Extract text from all pages
    text_parts: list[str] = []
    for page in doc:
        text = page.get_text("text")
        if text.strip():
            text_parts.append(text)

    full_text = "\n\n".join(text_parts)
    word_count = len(full_text.split())

    # Detect if OCR is needed (very little text extracted)
    ocr_needed = word_count < 10 and page_count > 0

    ocr_confidence: float | None = None

    if ocr_needed:
        # Try Tesseract OCR first, fall back to PyMuPDF text blocks
        try:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]

            text_parts = []
            confidences: list[float] = []
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                ocr_text = pytesseract.image_to_string(img)
                try:
                    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                    for confidence in data.get("conf", []):
                        conf_value = float(confidence)
                        if conf_value >= 0:
                            confidences.append(conf_value / 100.0)
                except Exception:
                    pass
                if ocr_text.strip():
                    text_parts.append(ocr_text)
            full_text = "\n\n".join(text_parts)
            word_count = len(full_text.split())
            if confidences:
                ocr_confidence = round(sum(confidences) / len(confidences), 3)
        except ImportError:
            # Tesseract not available — fall back to PyMuPDF text blocks
            text_parts = []
            for page in doc:
                blocks = page.get_text("blocks")
                for block in blocks:
                    if block[6] == 0:
                        text_parts.append(block[4])
            full_text = "\n\n".join(text_parts)
            word_count = len(full_text.split())

    # Extract images
    slug = slugify(title)
    img_dir = images_dir / slug
    img_dir.mkdir(parents=True, exist_ok=True)
    image_count = 0

    for page_num, page in enumerate(doc):
        for img_idx, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n > 4:  # CMYK
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                img_name = f"page{page_num + 1}_img{img_idx + 1}.png"
                img_path = img_dir / img_name
                pix.save(str(img_path))
                image_count += 1
            except Exception:
                continue

    doc.close()

    # Build markdown content
    md_content = f"# {title}\n\n{full_text}"

    # Build frontmatter
    fm_data = {
        "title": title,
        "id": slug,
        "source": "local",
        "format": "pdf-extracted",
        "clipped_at": datetime.now(UTC).isoformat(),
        "word_count": word_count,
        "page_count": page_count,
        "content_hash": content_hash(pdf_path),
        "status": "raw",
        "ocr": ocr_needed,
    }
    if author:
        fm_data["author"] = author
    if ocr_confidence is not None:
        fm_data["ocr_confidence"] = ocr_confidence

    # Save markdown
    post = frontmatter.Post(md_content, **fm_data)
    output_path = raw_dir / f"{slug}.md"

    # Handle name conflicts
    counter = 2
    while output_path.exists():
        output_path = raw_dir / f"{slug}-{counter}.md"
        counter += 1

    output_path.write_text(frontmatter.dumps(post))

    # Preserve original PDF
    originals_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, originals_dir / pdf_path.name)

    # Clean up empty image dir
    if image_count == 0 and img_dir.exists():
        img_dir.rmdir()

    return output_path

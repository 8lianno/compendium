"""Pydantic models for YAML frontmatter in raw sources and wiki articles."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceFormat(StrEnum):
    MARKDOWN = "markdown"
    PDF_EXTRACTED = "pdf-extracted"
    HTML_RAW = "html-raw"
    CSV = "csv"


class SourceOrigin(StrEnum):
    WEB_CLIP = "web-clip"
    LOCAL = "local"


class SourceStatus(StrEnum):
    RAW = "raw"
    COMPILED = "compiled"
    ERROR = "error"


class RawSourceFrontmatter(BaseModel):
    """Frontmatter for raw source files in raw/."""

    title: str
    id: str
    source_url: str | None = None
    author: str | None = None
    clipped_at: datetime = Field(default_factory=datetime.now)
    format: SourceFormat = SourceFormat.MARKDOWN
    source: SourceOrigin = SourceOrigin.LOCAL
    word_count: int = 0
    page_count: int | None = None
    content_hash: str = ""
    status: SourceStatus = SourceStatus.RAW
    language: str = "en"
    ocr: bool = False
    partial: bool = False
    original_url: str | None = None


class ArticleOrigin(StrEnum):
    COMPILATION = "compilation"
    QA_OUTPUT = "qa-output"
    USER_FILED = "user-filed"


class ArticleStatus(StrEnum):
    PUBLISHED = "published"
    DRAFT = "draft"
    STALE = "stale"
    CONFLICT = "conflict"


class SourceReference(BaseModel):
    """Reference to a raw source with optional section references."""

    ref: str
    sections: list[str] = Field(default_factory=list)


class CompiledByInfo(BaseModel):
    """Metadata about which model compiled the article."""

    model: str
    tokens_used: int = 0


class WikiArticleFrontmatter(BaseModel):
    """Frontmatter for wiki articles in wiki/."""

    title: str
    id: str
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    origin: ArticleOrigin = ArticleOrigin.COMPILATION
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    compiled_by: CompiledByInfo | None = None
    word_count: int = 0
    status: ArticleStatus = ArticleStatus.PUBLISHED
    related: list[str] = Field(default_factory=list)
    referenced_by: list[str] = Field(default_factory=list)


class ReportFrontmatter(BaseModel):
    """Frontmatter for Q&A output reports."""

    title: str
    type: str = "report"
    query: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)
    sources_used: list[str] = Field(default_factory=list)
    tokens_used: int = 0
    filed_to_wiki: bool = False

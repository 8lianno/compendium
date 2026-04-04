"""Source ingestion — file drop, web clip, PDF extraction, dedup."""

from compendium.ingest.file_drop import BatchResult, IngestResult, ingest_batch, ingest_file

__all__ = ["BatchResult", "IngestResult", "ingest_batch", "ingest_file"]

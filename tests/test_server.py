"""Tests for the FastAPI app surfaces added for the v1.0 gap closure."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter
import pytest
from fastapi.testclient import TestClient

from compendium.core.wiki_fs import WikiFileSystem
from compendium.llm.provider import CompletionRequest, CompletionResponse, TokenPricing, TokenUsage
from compendium.server import create_app

if TYPE_CHECKING:
    from pathlib import Path


class FakeProvider:
    """Minimal fake provider for server/session tests."""

    name = "fake"
    model_name = "fake-model"
    context_window = 123_456
    pricing = TokenPricing(input_per_million=1.5, output_per_million=6.0)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            content=(
                '{"source":"raw-source","title":"Raw Source","summary":"Short summary",'
                '"claims":[],"concepts":["attention"],"findings":[],"limitations":[]}'
            ),
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            model=self.model_name,
        )

    async def test_connection(self) -> bool:
        return True


@pytest.fixture
def server_project(tmp_path: Path) -> WikiFileSystem:
    """Project fixture with one raw source and one wiki article."""
    wfs = WikiFileSystem(tmp_path / "project")
    wfs.init_project("Server Test Wiki")

    raw_post = frontmatter.Post(
        "# Attention\n\nAttention content.",
        title="Attention Source",
        id="attention-source",
        source="local",
        format="markdown",
        status="raw",
        word_count=2,
    )
    (wfs.raw_dir / "attention-source.md").write_text(frontmatter.dumps(raw_post))

    concepts_dir = wfs.wiki_dir / "concepts"
    concepts_dir.mkdir(exist_ok=True)
    article = frontmatter.Post(
        "# Attention\n\nSee also [[transformers]].",
        title="Attention",
        category="concepts",
        type="concept",
        sources=[{"ref": "raw/attention-source.md"}],
        origin="compilation",
        status="published",
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )
    (concepts_dir / "attention.md").write_text(frontmatter.dumps(article))
    (wfs.wiki_dir / "INDEX.md").write_text(
        "# Index\n\n## Concepts\n\n| Page | Type | Summary | Sources | Updated |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| [[concepts/attention|Attention]] | concept | Attention overview | 1 | 2026-04-04 |\n"
    )
    return wfs


@pytest.fixture
def client(server_project: WikiFileSystem) -> TestClient:
    """Create a test client for the server app."""
    return TestClient(create_app(str(server_project.root)))


def test_download_endpoint_blocks_traversal_and_serves_files(
    client: TestClient,
    server_project: WikiFileSystem,
) -> None:
    report_path = server_project.reports_dir / "sample.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# Sample report")

    response = client.get("/api/download/output/reports/sample.md")
    assert response.status_code == 200
    assert response.text == "# Sample report"

    blocked = client.get("/api/download/%2E%2E/%2E%2E/etc/passwd")
    assert blocked.status_code == 400


def test_graph_endpoint_includes_article_paths(client: TestClient) -> None:
    response = client.get("/api/graph")
    assert response.status_code == 200

    payload = response.json()
    assert payload["node_count"] == 1
    assert payload["nodes"][0]["path"] == "wiki/concepts/attention.md"


def test_settings_update_regenerates_schema_and_logs(
    client: TestClient,
    server_project: WikiFileSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("compendium.llm.factory.create_provider", lambda _cfg: FakeProvider())
    monkeypatch.setattr("compendium.llm.factory.get_api_key", lambda _provider: "saved-key")

    response = client.post(
        "/api/settings/model-assignments",
        json={
            "compilation": {"provider": "anthropic", "model": "claude-sonnet-test"},
            "qa": {"provider": "openai", "model": "gpt-test"},
            "lint_model": {"provider": "gemini", "model": "gemini-test"},
            "templates": {"default": "book-reading", "domain": "Reading notes"},
            "lint_settings": {"schedule": "weekly", "missing_data_web_search": True},
            "default_provider": "openai",
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "saved"
    assert "templates" in payload["changed"]
    assert payload["operations"]["compilation"]["context_window"] == 123456
    assert payload["operations"]["compilation"]["pricing"]["input_per_million"] == 1.5

    schema_text = (server_project.wiki_dir / "SCHEMA.md").read_text()
    assert "Template: `book-reading`" in schema_text
    assert "Reading notes" in schema_text

    log_text = (server_project.wiki_dir / "log.md").read_text()
    assert "schema-update | Settings updated" in log_text


def test_settings_provider_test_returns_context_and_pricing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("compendium.llm.factory.create_provider", lambda _cfg: FakeProvider())

    response = client.post(
        "/api/settings/test-provider",
        json={"provider": "anthropic", "model": "claude-sonnet-test"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider": "fake",
        "model": "fake-model",
        "context_window": 123456,
        "pricing": {"input_per_million": 1.5, "output_per_million": 6.0},
    }


def test_compile_session_interactive_roundtrip(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("compendium.llm.factory.create_provider", lambda _cfg: FakeProvider())

    async def fake_finalize(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "articles_count": 1,
            "concepts_count": 1,
            "conflicts_detected": 0,
            "sources_processed": 1,
            "mode": "interactive",
        }

    monkeypatch.setattr(
        "compendium.pipeline.sessions._finalize_compile_from_summaries",
        fake_finalize,
    )

    start = client.post("/api/compile/session", json={"mode": "interactive"})
    assert start.status_code == 200
    start_payload = start.json()
    assert start_payload["status"] == "awaiting_approval"
    assert start_payload["pending_summary"]["summary"] == "Short summary"

    session_id = start_payload["session_id"]
    approve = client.post(f"/api/compile/session/{session_id}/approve", json={"approve": True})
    assert approve.status_code == 200
    approve_payload = approve.json()
    assert approve_payload["status"] == "completed"
    assert approve_payload["result"]["mode"] == "interactive"


def test_update_session_batch_roundtrip(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("compendium.llm.factory.create_provider", lambda _cfg: FakeProvider())

    async def fake_incremental_update(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"articles_added": 1, "sources_processed": 1}

    monkeypatch.setattr("compendium.pipeline.sessions.incremental_update", fake_incremental_update)

    response = client.post("/api/update/session", json={"paths": ["raw/attention-source.md"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["result"]["articles_added"] == 1


def test_upload_endpoint_accepts_duplicate_mode(client: TestClient) -> None:
    response = client.post(
        "/api/ingest/upload",
        data={"duplicate_mode": "keep_both"},
        files={"files": ("upload.md", "# Uploaded\n\nBody", "text/markdown")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicate_mode"] == "keep_both"
    assert payload["succeeded"] == 1


def test_lint_endpoint_writes_report_and_reason(
    client: TestClient,
    server_project: WikiFileSystem,
) -> None:
    response = client.get("/api/lint")
    assert response.status_code == 200
    payload = response.json()
    assert payload["reason"] == "manual"
    assert (server_project.wiki_dir / "HEALTH_REPORT.md").exists()
    assert "lint | Lint run" in (server_project.wiki_dir / "log.md").read_text()

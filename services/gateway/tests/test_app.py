"""End-to-end wiring tests for the gateway over NATIVE engines."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zeropark_gateway.main import create_app  # noqa: E402
from zeropark_gateway.auth import get_current_user  # noqa: E402

@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    # Native engines need no service URLs; just point artifact output at tmp.
    monkeypatch.setenv("ZEROPARK_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("ZEROPARK_SEARCH__BASE_URL", raising=False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "test_user", "role": "user"}
    return TestClient(app)


def test_health_lists_native_engines(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    ids = {p["id"] for p in body["providers"]}
    assert {"local-crawl", "zeropark_engines.slides.pptx"}.issubset(ids)
    assert "crawl" in body["capabilities"] and "slides" in body["capabilities"]


def test_route_research_reports_missing_search_and_research(client: TestClient) -> None:
    body = client.post("/route", json={"prompt": "x", "mode": "research"}).json()
    assert body["resolved"]["crawl"] == "local-crawl"
    assert "search" in body["missing"]
    assert "research" in body["missing"]


def test_slides_task_generates_real_pptx(client: TestClient, tmp_path) -> None:
    resp = client.post(
        "/api/v1/tasks",
        json={
            "mode": "slides",
            "prompt": "Company overview",
            "params": {"title": "Overview", "outline": [{"title": "Intro", "bullets": ["Hi"]}]},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "task_id" in body
    assert "slides" in body["plan"]


def test_search_without_backend_is_503(client: TestClient) -> None:
    assert client.post("/search", json={"query": "x"}).status_code == 503

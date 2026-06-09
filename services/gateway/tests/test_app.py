"""End-to-end wiring tests for the gateway over NATIVE engines."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zeropark_gateway.main import create_app  # noqa: E402


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    # Native engines need no service URLs; just point artifact output at tmp.
    monkeypatch.setenv("ZEROPARK_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("ZEROPARK_SEARCH__BASE_URL", raising=False)
    return TestClient(create_app())


def test_health_lists_native_engines(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    ids = {p["id"] for p in body["providers"]}
    assert ids == {"local-crawl", "pptx-slides"}
    assert "crawl" in body["capabilities"] and "slides" in body["capabilities"]


def test_route_research_reports_missing_search_and_research(client: TestClient) -> None:
    body = client.post("/route", json={"prompt": "x", "mode": "research"}).json()
    assert body["resolved"]["crawl"] == "local-crawl"
    assert "search" in body["missing"]
    assert "research" in body["missing"]


def test_slides_task_generates_real_pptx(client: TestClient, tmp_path) -> None:
    resp = client.post(
        "/tasks",
        json={
            "mode": "slides",
            "prompt": "Company overview",
            "params": {"title": "Overview", "outline": [{"title": "Intro", "bullets": ["Hi"]}]},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    deck = body["artifacts"][0]
    assert deck["kind"] == "deck"
    assert Path(deck["uri"]).exists()


def test_search_without_backend_is_503(client: TestClient) -> None:
    assert client.post("/search", json={"query": "x"}).status_code == 503

"""Usage metering: counters increment per task and are exposed at /api/v1/usage."""

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
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROPARK_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("ZEROPARK_SEARCH__BASE_URL", raising=False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u", "role": "user"}
    return TestClient(app)


def test_usage_counters_increment_per_task(client):
    assert client.get("/api/v1/usage").json()["tasks_total"] == 0

    resp = client.post(
        "/api/v1/tasks",
        json={
            "mode": "slides",
            "prompt": "deck",
            "params": {"title": "T", "outline": [{"title": "A", "bullets": ["x"]}]},
        },
    )
    assert resp.status_code == 200

    usage = client.get("/api/v1/usage").json()
    assert usage["tasks_total"] == 1
    assert usage["tasks_failed"] == 0
    assert usage["by_capability"] == {"slides": 1}

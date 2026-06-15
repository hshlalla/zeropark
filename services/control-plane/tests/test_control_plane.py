"""Control plane: deployment CRUD, license-keyed heartbeat, online status."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROPARK_CP_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv(
        "CONTROL_PLANE_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/cp.db"
    )
    # module reads env at import time — reload to pick up the test DB
    for mod in list(sys.modules):
        if mod.startswith("zeropark_control"):
            del sys.modules[mod]
    from zeropark_control.main import create_app

    # context manager runs the lifespan (creates tables)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_dashboard_served_at_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Zeropark Control Plane" in response.text


def test_requires_admin_token(client):
    assert client.get("/api/v1/deployments").status_code == 401
    bad = client.get("/api/v1/deployments", headers={"X-Admin-Token": "wrong"})
    assert bad.status_code == 401


def test_deployment_lifecycle_and_heartbeat(client):
    # create
    created = client.post(
        "/api/v1/deployments",
        headers=ADMIN,
        json={
            "name": "Samsung DS Agent",
            "client_name": "Samsung",
            "base_url": "https://agent.samsung.example.com",
            "profile": {"branding": {"product_name": "S-Agent"}, "features": {"browse": False}},
        },
    ).json()
    assert created["license_key"].startswith("zp_")
    assert created["online"] is False
    dep_id, license_key = created["id"], created["license_key"]

    # heartbeat with bad key is rejected
    bad = client.post(
        "/api/v1/heartbeat",
        json={"deployment_id": dep_id, "license_key": "zp_wrong"},
    )
    assert bad.status_code == 401

    # valid heartbeat updates status, stores usage, and returns the live profile
    hb = client.post(
        "/api/v1/heartbeat",
        json={
            "deployment_id": dep_id,
            "license_key": license_key,
            "version": "0.1.0",
            "capabilities": ["crawl", "slides"],
            "usage": {"tasks_total": 12, "tasks_failed": 1, "tokens_total": 3400,
                      "by_capability": {"slides": 12}},
        },
    )
    assert hb.status_code == 200
    assert hb.json()["profile"]["features"] == {"browse": False}

    fetched = client.get(f"/api/v1/deployments/{dep_id}", headers=ADMIN).json()
    assert fetched["online"] is True
    assert fetched["version"] == "0.1.0"
    assert fetched["capabilities"] == ["crawl", "slides"]
    assert fetched["usage"]["tasks_total"] == 12
    assert fetched["usage"]["tokens_total"] == 3400

    # deactivating the license blocks heartbeats
    client.patch(f"/api/v1/deployments/{dep_id}", headers=ADMIN, json={"is_active": False})
    blocked = client.post(
        "/api/v1/heartbeat",
        json={"deployment_id": dep_id, "license_key": license_key},
    )
    assert blocked.status_code == 403

    # usage time-series: one record per heartbeat with usage
    client.patch(f"/api/v1/deployments/{dep_id}", headers=ADMIN, json={"is_active": True})
    client.post("/api/v1/heartbeat", json={
        "deployment_id": dep_id, "license_key": license_key,
        "usage": {"tasks_total": 20, "tokens_total": 5000},
    })
    history = client.get(f"/api/v1/deployments/{dep_id}/usage-history", headers=ADMIN).json()["records"]
    assert len(history) == 2  # first heartbeat + this one
    assert history[0]["usage"]["tasks_total"] == 20  # newest first

    # list filter by client
    listed = client.get("/api/v1/deployments", headers=ADMIN, params={"client": "Samsung"}).json()
    assert len(listed["deployments"]) == 1
    assert client.get("/api/v1/deployments", headers=ADMIN, params={"client": "LG"}).json()["deployments"] == []

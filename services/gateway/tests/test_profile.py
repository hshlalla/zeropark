"""Deployment profile endpoint + control-plane hot-reload application."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zeropark_gateway.main import create_app, apply_profile  # noqa: E402


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROPARK_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("ZEROPARK_SEARCH__BASE_URL", raising=False)
    monkeypatch.setenv("ZEROPARK_BRANDING__PRODUCT_NAME", "S-Agent")
    monkeypatch.setenv("ZEROPARK_BRANDING__CLIENT_NAME", "Samsung")
    return create_app()


def test_profile_endpoint_exposes_branding_and_capabilities(app):
    client = TestClient(app)
    body = client.get("/api/v1/profile").json()
    assert body["branding"]["product_name"] == "S-Agent"
    assert body["branding"]["client_name"] == "Samsung"
    assert "crawl" in body["capabilities"]


def test_apply_profile_hot_reloads_features_and_branding(app):
    client = TestClient(app)
    assert "crawl" in client.get("/api/v1/profile").json()["capabilities"]

    changed = apply_profile(
        app,
        {"branding": {"primary_color": "#FF0000"}, "features": {"crawl": False}},
    )
    assert changed is True

    body = client.get("/api/v1/profile").json()
    assert body["branding"]["primary_color"] == "#FF0000"
    assert body["branding"]["product_name"] == "S-Agent"  # untouched keys survive
    assert "crawl" not in body["capabilities"]            # engine removed live

    # same profile again -> no change reported
    assert apply_profile(app, {"features": {"crawl": False}}) is False

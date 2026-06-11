"""Permission model tests: apps registry (admin builds, user uses) and
RAG collections (role-gated read access)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zeropark_gateway.main import create_app  # noqa: E402
from zeropark_gateway.auth import get_current_user  # noqa: E402


class RoleSwitch:
    """Dependency override whose role can be flipped mid-test."""

    def __init__(self):
        self.role = "admin"

    def __call__(self):
        return {"user_id": f"test_{self.role}", "role": self.role}


@pytest.fixture
def ctx(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROPARK_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("ZEROPARK_SEARCH__BASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    # database.py reads DATABASE_URL at import — rebuild engine for isolation
    import zeropark_core.database as db
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    db.engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )
    db.AsyncSessionLocal = sessionmaker(db.engine, class_=AsyncSession, expire_on_commit=False)
    # modules captured AsyncSessionLocal by reference at import time
    import zeropark_gateway.apps as apps_mod
    import zeropark_gateway.knowledge as knowledge_mod
    apps_mod.AsyncSessionLocal = db.AsyncSessionLocal
    knowledge_mod.AsyncSessionLocal = db.AsyncSessionLocal

    app = create_app()
    switch = RoleSwitch()
    app.dependency_overrides[get_current_user] = switch
    with TestClient(app) as client:
        yield client, switch


def test_apps_admin_builds_user_uses(ctx):
    client, switch = ctx

    # admin creates a published app and a draft
    switch.role = "admin"
    published = client.post(
        "/api/v1/apps",
        json={"name": "고객지원봇", "mode": "chat", "published": True},
    )
    assert published.status_code == 200
    draft = client.post(
        "/api/v1/apps",
        json={"name": "작업중봇", "mode": "chat", "published": False},
    )
    assert draft.status_code == 200
    app_id = published.json()["id"]

    # admin sees both; user sees ONLY the published one
    assert len(client.get("/api/v1/apps").json()["apps"]) == 2
    switch.role = "user"
    user_apps = client.get("/api/v1/apps").json()["apps"]
    assert [a["name"] for a in user_apps] == ["고객지원봇"]

    # user can read the published app, cannot create or delete
    assert client.get(f"/api/v1/apps/{app_id}").status_code == 200
    assert client.post("/api/v1/apps", json={"name": "x", "mode": "chat"}).status_code == 403
    assert client.delete(f"/api/v1/apps/{app_id}").status_code == 403

    # admin deletes
    switch.role = "admin"
    assert client.delete(f"/api/v1/apps/{app_id}").status_code == 200


def test_rag_collections_role_gating(ctx):
    client, switch = ctx

    # admin creates an admin-only collection
    switch.role = "admin"
    created = client.post(
        "/api/v1/rag/collections",
        json={"name": "인사기밀", "allowed_roles": ["admin"]},
    )
    assert created.status_code == 200
    secret_id = created.json()["id"]

    # admin sees default + secret; user sees only default
    admin_ids = {c["id"] for c in client.get("/api/v1/rag/collections").json()["collections"]}
    assert {"default", secret_id} <= admin_ids
    switch.role = "user"
    user_ids = {c["id"] for c in client.get("/api/v1/rag/collections").json()["collections"]}
    assert "default" in user_ids and secret_id not in user_ids

    # user cannot create collections nor upload into the secret one
    assert client.post(
        "/api/v1/rag/collections", json={"name": "x"}
    ).status_code == 403
    upload = client.post(
        f"/api/v1/rag/upload?collection_id={secret_id}",
        files=[("files", ("a.txt", b"text", "text/plain"))],
    )
    assert upload.status_code == 403

    # default collection cannot be deleted even by admin
    switch.role = "admin"
    assert client.delete("/api/v1/rag/collections/default").status_code == 400

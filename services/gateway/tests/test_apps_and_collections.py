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


def test_saved_workflow_crud_roundtrip(ctx):
    client, switch = ctx
    switch.role = "admin"
    definition = {
        "nodes": [{"id": "n1", "position": {"x": 0, "y": 0}, "data": {"type": "input", "x": "1"}}],
        "edges": [],
    }
    created = client.post("/api/v1/workflow/saved", json={"name": "수집봇", "definition": definition}).json()
    wf_id = created["id"]

    listed = client.get("/api/v1/workflow/saved").json()["workflows"]
    assert any(w["id"] == wf_id for w in listed)

    fetched = client.get(f"/api/v1/workflow/saved/{wf_id}").json()
    assert fetched["definition"] == definition  # export == import payload

    assert client.put(
        f"/api/v1/workflow/saved/{wf_id}",
        json={"name": "수집봇v2", "definition": definition},
    ).status_code == 200
    assert client.delete(f"/api/v1/workflow/saved/{wf_id}").status_code == 200


def test_publish_and_run_saved_workflow(ctx):
    """A saved workflow can be published as an App and run by id — the path the
    dashboard uses for a workflow-mode App."""
    client, switch = ctx
    switch.role = "admin"

    # input -> output workflow that just echoes a context value (no LLM needed)
    definition = {
        "nodes": [
            {"id": "start", "data": {"type": "input", "topic": "zeropark"}},
            {"id": "end", "data": {"type": "output", "keys": ["topic"]}},
        ],
        "edges": [{"source": "start", "target": "end"}],
    }
    wf_id = client.post(
        "/api/v1/workflow/saved", json={"name": "echo-flow", "definition": definition}
    ).json()["id"]

    # publish as an App
    app = client.post(
        "/api/v1/apps",
        json={"name": "Echo", "mode": "workflow", "params": {"workflow_id": wf_id}, "published": True},
    ).json()
    assert app["params"]["workflow_id"] == wf_id

    # run the saved workflow by id
    run = client.post(f"/api/v1/workflow/saved/{wf_id}/run", json={"prompt": "hello"})
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "success"
    # input node populated context; output node collected it; prompt surfaced
    assert body["results"]["topic"] == "zeropark"
    assert body["results"]["prompt"] == "hello"

    assert client.post("/api/v1/workflow/saved/does-not-exist/run", json={}).status_code == 404


def test_feedback_flow(ctx):
    client, switch = ctx
    switch.role = "user"
    sid = client.post("/api/v1/conversations", json={}).json()["id"]
    assert client.post(
        f"/api/v1/conversations/{sid}/feedback",
        json={"rating": "down", "message_content": "엉뚱한 답", "comment": "맥락 무시"},
    ).status_code == 200
    # users cannot read the admin review queue
    assert client.get("/api/v1/admin/feedback").status_code == 403
    switch.role = "admin"
    items = client.get("/api/v1/admin/feedback").json()["feedback"]
    assert items and items[0]["rating"] == "down" and items[0]["comment"] == "맥락 무시"


def test_pdf_and_docx_extraction():
    import io
    from pypdf import PdfWriter
    from docx import Document as DocxDocument
    from zeropark_gateway.knowledge import extract_text

    # docx with a known sentence
    buf = io.BytesIO()
    doc = DocxDocument()
    doc.add_paragraph("보증 기간은 7년입니다.")
    doc.save(buf)
    assert "보증 기간은 7년" in extract_text("policy.docx", buf.getvalue())

    # blank-page pdf parses without error (text extraction returns empty)
    pdf_buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf_buf)
    assert extract_text("doc.pdf", pdf_buf.getvalue()) == ""

    # plain text fallback
    assert extract_text("a.txt", "hello".encode()) == "hello"


def test_rag_task_path_enforces_collections(ctx, monkeypatch):
    """Agents run RAG through /api/v1/tasks — the gateway must inject the
    caller's readable collections there too, and pinned ids can only narrow."""
    client, switch = ctx

    switch.role = "admin"
    secret_id = client.post(
        "/api/v1/rag/collections",
        json={"name": "기밀", "allowed_roles": ["admin"]},
    ).json()["id"]

    captured: dict = {}

    class FakeRag:
        id = "fake-rag"
        name = "fake"
        capabilities = frozenset()

        async def execute(self, task, task_id):
            captured["params"] = task.params
            from zeropark_core.models import TaskResult, TaskStatus
            from zeropark_core.capabilities import Capability
            return TaskResult(
                task_id=task_id, status=TaskStatus.SUCCEEDED,
                capability=Capability.RAG, provider_id=self.id,
            )

    original_router = client.app.state.router

    class FakeRouter:
        def plan(self, mode):
            return original_router.plan(mode)

        def select(self, capability, prefer=None):
            return FakeRag()

    client.app.state.router = FakeRouter()

    try:
        # user task: allowed set must EXCLUDE the admin-only collection
        switch.role = "user"
        resp = client.post("/api/v1/tasks", json={"mode": "rag", "prompt": "question"})
        assert resp.status_code == 200
        allowed = captured["params"]["allowed_collection_ids"]
        assert "default" in allowed and secret_id not in allowed

        # user pinning the secret collection gets an EMPTY allowed set, not access
        resp = client.post(
            "/api/v1/tasks",
            json={"mode": "rag", "prompt": "q", "params": {"collection_ids": [secret_id]}},
        )
        assert resp.status_code == 200
        assert captured["params"]["allowed_collection_ids"] == []

        # admin task: secret collection included
        switch.role = "admin"
        client.post("/api/v1/tasks", json={"mode": "rag", "prompt": "q"})
        assert secret_id in captured["params"]["allowed_collection_ids"]
    finally:
        client.app.state.router = original_router

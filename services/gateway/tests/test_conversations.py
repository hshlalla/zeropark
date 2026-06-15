"""Conversation memory: sessions persist turns and inject history into tasks."""

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
    import zeropark_core.database as db
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    db.engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/conv.db", connect_args={"check_same_thread": False}
    )
    db.AsyncSessionLocal = sessionmaker(db.engine, class_=AsyncSession, expire_on_commit=False)
    import zeropark_gateway.conversations as conv_mod
    conv_mod.AsyncSessionLocal = db.AsyncSessionLocal

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": "user"}
    with TestClient(app) as test_client:
        yield test_client


def test_variables_and_summary_injection(client, monkeypatch):
    """Conversation variables substitute into the system prompt and the rolling
    summary rides along as a system history entry."""
    import anyio
    import zeropark_gateway.conversations as conv

    session_id = client.post("/api/v1/conversations", json={"app_id": "a"}).json()["id"]

    # store variables via the endpoint
    r = client.patch(
        f"/api/v1/conversations/{session_id}/variables",
        json={"values": {"name": "홍길동", "product": "Galaxy"}},
    )
    assert r.status_code == 200

    # simulate an existing rolling summary
    async def set_summary():
        async with conv.AsyncSessionLocal() as db:
            from zeropark_core.models_db import ChatSession
            s = await db.get(ChatSession, session_id)
            s.summary = "사용자는 갤럭시 보증 연장을 문의했다."
            await db.commit()
    anyio.run(set_summary)

    async def run_apply():
        return await conv.apply_session_context(
            {"system": "{{name}}님의 {{product}} 상담사다."}, session_id, "u1"
        )
    params = anyio.run(run_apply)

    assert params["system"] == "홍길동님의 Galaxy 상담사다."
    roles = [h["role"] for h in params["history"]]
    assert roles[0] == "system" and "보증 연장" in params["history"][0]["content"]
    assert any("홍길동" in h["content"] for h in params["history"] if h["role"] == "system")


def test_rolling_summary_trigger(client, monkeypatch):
    """Past the trigger, append_turn schedules a summary that folds old turns."""
    import anyio
    import zeropark_gateway.conversations as conv

    calls: dict = {}

    async def fake_summarize(existing, turns):
        calls["turns"] = len(turns)
        return f"요약({len(turns)}턴)"

    monkeypatch.setattr(conv, "summarize_fn", fake_summarize)
    session_id = client.post("/api/v1/conversations", json={}).json()["id"]

    async def fill():
        # 16 exchanges = 32 messages > SUMMARY_TRIGGER(30)
        for i in range(16):
            await conv.append_turn(session_id, f"질문{i}", f"답{i}")
        # append_turn fire-and-forgets the summary task; run it directly for determinism
        await conv._update_summary(session_id)
        async with conv.AsyncSessionLocal() as db:
            from zeropark_core.models_db import ChatSession
            return (await db.get(ChatSession, session_id)).summary
    summary = anyio.run(fill)

    assert summary == f"요약({32 - conv.HISTORY_WINDOW}턴)"
    assert calls["turns"] == 32 - conv.HISTORY_WINDOW


def test_conversation_crud_and_isolation(client):
    created = client.post("/api/v1/conversations", json={"app_id": "app1"}).json()
    session_id = created["id"]

    listed = client.get("/api/v1/conversations", params={"app_id": "app1"}).json()
    assert [c["id"] for c in listed["conversations"]] == [session_id]

    # another user's session is not visible / not readable
    client.app.dependency_overrides[get_current_user] = lambda: {"user_id": "u2", "role": "user"}
    assert client.get("/api/v1/conversations").json()["conversations"] == []
    assert client.get(f"/api/v1/conversations/{session_id}/messages").status_code == 403
    assert client.delete(f"/api/v1/conversations/{session_id}").status_code == 403

    client.app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": "user"}
    assert client.delete(f"/api/v1/conversations/{session_id}").status_code == 200


def test_task_with_session_injects_history_and_persists_turns(client):
    """A chat task run inside a session must see prior turns (params.history)
    and append the new exchange afterwards."""
    from zeropark_core.capabilities import Capability
    from zeropark_core.models import Artifact, TaskResult, TaskStatus

    session_id = client.post("/api/v1/conversations", json={"app_id": "app1"}).json()["id"]

    captured: dict = {}

    class FakeChat:
        id = "fake-chat"
        name = "fake"
        capabilities = frozenset()

        async def execute(self, task, task_id):
            captured["history"] = task.params.get("history")
            return TaskResult(
                task_id=task_id, status=TaskStatus.SUCCEEDED,
                capability=Capability.CHAT, provider_id=self.id,
                artifacts=[Artifact(id="a1", kind="message", inline="I will remember 42.")],
            )

    original_router = client.app.state.router

    class FakeRouter:
        def plan(self, mode):
            return original_router.plan(mode)

        def select(self, capability, prefer=None):
            return FakeChat()

    client.app.state.router = FakeRouter()
    try:
        # turn 1: no history yet
        r1 = client.post(
            "/api/v1/tasks",
            json={"mode": "chat", "prompt": "Remember 42", "session_id": session_id},
        )
        assert r1.status_code == 200
        assert captured["history"] == []

        # turn 2: previous user+assistant messages are injected
        r2 = client.post(
            "/api/v1/tasks",
            json={"mode": "chat", "prompt": "What number?", "session_id": session_id},
        )
        assert r2.status_code == 200
        assert captured["history"] == [
            {"role": "user", "content": "Remember 42"},
            {"role": "assistant", "content": "I will remember 42."},
        ]

        # messages endpoint shows the full transcript (2 exchanges = 4 rows)
        messages = client.get(f"/api/v1/conversations/{session_id}/messages").json()["messages"]
        assert len(messages) == 4
        assert messages[0]["content"] == "Remember 42"

        # session title auto-set from the first user message
        conversations = client.get("/api/v1/conversations").json()["conversations"]
        assert conversations[0]["title"] == "Remember 42"
    finally:
        client.app.state.router = original_router

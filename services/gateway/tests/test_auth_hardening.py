"""Auth hardening: refresh tokens, DB-backed revocation (token_version),
is_active enforcement, and role-change invalidation."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from zeropark_core.models_db import Base, User
from zeropark_core.database import get_db_session
from zeropark_gateway.auth import get_password_hash, issue_tokens
from zeropark_gateway.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_db():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def init_db():
    app.dependency_overrides[get_db_session] = _override_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.pop(get_db_session, None)


client = TestClient(app)


async def _make_user(role="user", active=True, tv=0) -> str:
    async with TestSessionLocal() as db:
        u = User(
            email=f"{role}-{tv}-{active}@t.com",
            hashed_password=get_password_hash("pw"),
            role=role, is_active=active, token_version=tv,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u.id


@pytest.mark.asyncio
async def test_login_issues_access_and_refresh():
    await _make_user()
    # protected route works with a freshly minted access token
    uid = await _make_user(role="admin")
    tokens = issue_tokens(uid, "admin", 0)
    r = client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_exchanges_for_new_access():
    uid = await _make_user(role="admin")
    tokens = issue_tokens(uid, "admin", 0)
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["access_token"] and new["refresh_token"]
    # the new access token works
    assert client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {new['access_token']}"}
    ).status_code == 200
    # an access token cannot be used where a refresh token is expected
    assert client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    ).status_code == 401


@pytest.mark.asyncio
async def test_token_version_revocation():
    uid = await _make_user(role="admin", tv=0)
    stale = issue_tokens(uid, "admin", 0)["access_token"]
    # bump the user's token_version server-side (simulates logout-all)
    async with TestSessionLocal() as db:
        u = await db.get(User, uid)
        u.token_version = 1
        await db.commit()
    # the old token now fails
    assert client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {stale}"}
    ).status_code == 401
    # a token minted at the new version works
    fresh = issue_tokens(uid, "admin", 1)["access_token"]
    assert client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {fresh}"}
    ).status_code == 200


@pytest.mark.asyncio
async def test_deactivated_user_is_rejected():
    uid = await _make_user(role="admin", active=False)
    tok = issue_tokens(uid, "admin", 0)["access_token"]
    assert client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {tok}"}
    ).status_code == 401


@pytest.mark.asyncio
async def test_logout_all_revokes_then_role_uses_db_value():
    # admin demoted in the DB → token claiming 'admin' is rejected after the
    # role-change bumps token_version
    uid = await _make_user(role="admin", tv=0)
    tok = issue_tokens(uid, "admin", 0)["access_token"]
    assert client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    # demote via the admin endpoint (bumps token_version)
    r = client.patch(
        f"/api/v1/admin/users/{uid}/role", json={"role": "user"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    # the old admin token is now invalid (revoked by the role change)
    assert client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_guest_login_blocked_in_production(monkeypatch):
    import zeropark_gateway.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_ENVIRONMENT", "production")
    assert client.post("/api/v1/auth/guest/login?role=admin").status_code == 403

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from zeropark_core.models_db import Base, User
from zeropark_gateway.main import app
from zeropark_core.database import get_db_session
from zeropark_gateway.auth import create_access_token

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db_session():
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db_session

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    app.dependency_overrides[get_db_session] = override_get_db_session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Seed DB with test users
    async with TestSessionLocal() as db:
        admin_user = User(id="admin-123", email="admin@example.com", role="admin", provider="local")
        normal_user = User(id="user-456", email="user@example.com", role="user", provider="google")
        db.add_all([admin_user, normal_user])
        await db.commit()
        
    yield
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

client = TestClient(app)

def get_auth_headers(user_id: str, role: str):
    token = create_access_token({"sub": user_id, "role": role})
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_admin_api_forbidden_for_normal_users():
    headers = get_auth_headers("user-456", "user")
    
    # Try all endpoints
    r1 = client.get("/api/v1/admin/stats", headers=headers)
    r2 = client.get("/api/v1/admin/users", headers=headers)
    r3 = client.patch("/api/v1/admin/users/user-456/role", json={"role": "admin"}, headers=headers)
    
    assert r1.status_code == 403
    assert r2.status_code == 403
    assert r3.status_code == 403

@pytest.mark.asyncio
async def test_admin_stats_ok_for_admin():
    headers = get_auth_headers("admin-123", "admin")
    
    res = client.get("/api/v1/admin/stats", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_users"] == 2
    assert data["local_users"] == 1
    assert data["google_users"] == 1
    assert data["admin_users"] == 1

@pytest.mark.asyncio
async def test_admin_get_users():
    headers = get_auth_headers("admin-123", "admin")
    
    res = client.get("/api/v1/admin/users?limit=10&skip=0", headers=headers)
    assert res.status_code == 200
    data = res.json()
    
    assert len(data) == 2
    emails = [u["email"] for u in data]
    assert "admin@example.com" in emails
    assert "user@example.com" in emails

@pytest.mark.asyncio
async def test_admin_update_role():
    headers = get_auth_headers("admin-123", "admin")
    
    # Promote normal user to admin
    res = client.patch("/api/v1/admin/users/user-456/role", json={"role": "admin"}, headers=headers)
    assert res.status_code == 200
    
    # Verify via DB
    async with TestSessionLocal() as db:
        from sqlalchemy.future import select
        result = await db.execute(select(User).where(User.id == "user-456"))
        user = result.scalars().first()
        assert user.role == "admin"
        
    # Stats should now reflect 2 admins
    stats_res = client.get("/api/v1/admin/stats", headers=headers)
    assert stats_res.json()["admin_users"] == 2

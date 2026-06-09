import pytest
import pytest_asyncio
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from zeropark_core.models_db import Base, User
from zeropark_gateway.main import app
from zeropark_core.database import get_db_session

# Test DB Setup
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db_session():
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db_session

@pytest_asyncio.fixture(autouse=True)
async def init_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

client = TestClient(app)

@pytest.mark.asyncio
async def test_google_login_redirect():
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 307
    assert "accounts.google.com/o/oauth2/v2/auth" in response.headers["location"]

@pytest.mark.asyncio
@patch("zeropark_gateway.auth.httpx.AsyncClient.post")
@patch("zeropark_gateway.auth.httpx.AsyncClient.get")
async def test_google_callback_new_user(mock_get, mock_post):
    # Mock token response
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "fake-google-token"}
    mock_post.return_value = mock_token_resp
    
    # Mock profile response
    mock_profile_resp = MagicMock()
    mock_profile_resp.status_code = 200
    mock_profile_resp.json.return_value = {
        "email": "test@google.com",
        "id": "google-1234",
        "name": "Test User"
    }
    mock_get.return_value = mock_profile_resp
    
    # Actually make the request
    response = client.get("/auth/google/callback?code=fake-code")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "test@google.com"
    assert data["user"]["role"] == "user"

@pytest.mark.asyncio
@patch("zeropark_gateway.auth.httpx.AsyncClient.post")
@patch("zeropark_gateway.auth.httpx.AsyncClient.get")
async def test_google_callback_existing_user(mock_get, mock_post):
    # Setup test user directly in DB first
    async with TestSessionLocal() as db:
        user = User(email="existing@google.com", provider="local", role="admin")
        db.add(user)
        await db.commit()

    # Mock token response
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "fake-google-token-2"}
    mock_post.return_value = mock_token_resp
    
    # Mock profile response matching existing user email
    mock_profile_resp = MagicMock()
    mock_profile_resp.status_code = 200
    mock_profile_resp.json.return_value = {
        "email": "existing@google.com",
        "id": "google-9999",
        "name": "Existing User"
    }
    mock_get.return_value = mock_profile_resp
    
    response = client.get("/auth/google/callback?code=fake-code-2")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "existing@google.com"
    # Role should remain admin since we upserted
    assert data["user"]["role"] == "admin"
    
    # Check if DB was updated with new provider info
    async with TestSessionLocal() as db:
        from sqlalchemy.future import select
        result = await db.execute(select(User).where(User.email == "existing@google.com"))
        updated_user = result.scalars().first()
        assert updated_user.provider == "google"
        assert updated_user.provider_id == "google-9999"

import os
import secrets
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, APIRouter, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from zeropark_core.database import get_db_session
from zeropark_core.models_db import User

# OAuth Settings
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "your-google-client-id")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "your-google-client-secret")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Secret keys and algorithm.
# Production MUST provide a fixed SECRET_KEY — otherwise every restart mints a
# new signing key, silently invalidating all tokens, and multiple instances
# can't validate each other's tokens. We refuse to boot 'production' without it.
SECRET_KEY = os.environ.get("SECRET_KEY")
_ENVIRONMENT = os.environ.get("ZEROPARK_ENVIRONMENT", "local").lower()
if not SECRET_KEY:
    if _ENVIRONMENT == "production":
        raise RuntimeError(
            "SECRET_KEY is required in production. Set the SECRET_KEY environment "
            "variable to a fixed random value (e.g. `python -c \"import secrets; "
            "print(secrets.token_hex(32))\"`)."
        )
    print("WARNING: SECRET_KEY not set - generating an ephemeral key (dev only). "
          "Tokens will not survive a restart. Set SECRET_KEY for stable sessions.")
    SECRET_KEY = secrets.token_hex(32)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 8))  # 8h
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 30))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def _is_guest(user_id: str) -> bool:
    """Guest tokens (mock login for dev/demo) carry no DB row, so the DB-based
    revocation/role checks are skipped for them."""
    return isinstance(user_id, str) and user_id.startswith("guest-")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    to_encode = data.copy()
    to_encode.update({
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "type": "refresh",
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def issue_tokens(user_id: str, role: str, token_version: int = 0) -> dict:
    """Both tokens carry the user's current token_version; bumping it server-side
    invalidates every token already in the wild."""
    claims = {"sub": user_id, "role": role, "tv": token_version}
    return {
        "access_token": create_access_token(claims),
        "refresh_token": create_refresh_token(claims),
        "token_type": "bearer",
    }


async def _decode_and_verify(token: str, expected_type: str, db: AsyncSession) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise credentials_exception
    if payload.get("type") != expected_type:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # Guest tokens bypass DB checks (dev/demo only).
    if _is_guest(user_id):
        return {"user_id": user_id, "role": payload.get("role", "user")}

    # Real users: validate against the DB so deactivation, role changes, and
    # logout-all take effect immediately instead of waiting for token expiry.
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if user is None or not user.is_active:
        raise credentials_exception
    if payload.get("tv", 0) != (user.token_version or 0):
        raise credentials_exception  # token was revoked (logout-all / role change)
    return {"user_id": user.id, "role": user.role}  # role is the DB's current value


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db_session)):
    return await _decode_and_verify(token, "access", db)

async def get_current_admin_user(current_user: dict = Depends(get_current_user)):
    """Dependency that enforces admin-only access."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

@auth_router.post("/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db_session)):
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user or not user.hashed_password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    return issue_tokens(user.id, user.role, user.token_version or 0)


@auth_router.post("/refresh")
async def refresh_access_token(payload: dict, db: AsyncSession = Depends(get_db_session)):
    """Exchange a valid refresh token for a fresh access (+refresh) token pair.
    Re-validates against the DB, so revoked/deactivated users cannot refresh."""
    refresh_token = (payload or {}).get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token is required")
    verified = await _decode_and_verify(refresh_token, "refresh", db)
    # token_version is re-read inside issue path; fetch current value for real users
    user_id = verified["user_id"]
    if _is_guest(user_id):
        return issue_tokens(user_id, verified["role"], 0)
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User no longer valid")
    return issue_tokens(user.id, user.role, user.token_version or 0)


@auth_router.post("/logout-all")
async def logout_all(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    """Revoke every outstanding token for the caller by bumping token_version."""
    if _is_guest(current_user["user_id"]):
        return {"status": "ok", "note": "guest tokens are not tracked"}
    user = (await db.execute(select(User).where(User.id == current_user["user_id"]))).scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return {"status": "ok", "message": "All sessions revoked."}

@auth_router.get("/google/login")
async def google_login():
    """Redirects the user to Google's OAuth 2.0 consent screen."""
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
    )
    return RedirectResponse(auth_url)

@auth_router.get("/google/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_db_session)):
    """Handles the OAuth callback, exchanges code for token, and registers/logs in the user."""
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    
    async with httpx.AsyncClient() as client:
        # 1. Exchange code for access token
        token_response = await client.post(token_url, data=data)
        if token_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange Google token")
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        # 2. Get User Info
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        userinfo_response = await client.get(userinfo_url, headers=headers)
        if userinfo_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Google profile")
            
        profile = userinfo_response.json()
        email = profile.get("email")
        google_id = profile.get("id")
        name = profile.get("name")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google profile did not return an email")
            
        # 3. Upsert user in DB
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalars().first()
        
        if not user:
            # Create new user via OAuth
            user = User(
                email=email,
                full_name=name,
                provider="google",
                provider_id=google_id,
                role="user"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            # Update existing user's provider info if needed
            if user.provider != "google":
                user.provider = "google"
                user.provider_id = google_id
                await db.commit()
                await db.refresh(user)
                
        # 4. Generate our own token pair (API-first; the SPA stores them).
        tokens = issue_tokens(user.id, user.role, user.token_version or 0)
        return {**tokens, "user": {"email": user.email, "role": user.role}}


@auth_router.post("/guest/login")
async def guest_login(role: str = "admin"):
    """Mock login for dev/demo — disabled in production. Guest tokens bypass
    DB-backed revocation/role checks, so they must never exist in production."""
    if _ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="Guest login is disabled in production.")
    tokens = issue_tokens(f"guest-{role}-001", role, 0)
    return {**tokens, "user": {"email": f"guest_{role}@zeropark.local", "role": role}}

import os
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

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# Secret keys and algorithm
SECRET_KEY = os.environ.get("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7") # Change in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Here we parse from JWT, but normally fetch from DB
    return {"user_id": user_id, "role": payload.get("role", "user")}

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
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(
        data={"sub": user.id, "role": user.role}
    )
    return {"access_token": access_token, "token_type": "bearer"}

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
                
        # 4. Generate our own JWT
        our_token = create_access_token(
            data={"sub": user.id, "role": user.role}
        )
        return {"access_token": our_token, "token_type": "bearer", "user": {"email": user.email, "role": user.role}}

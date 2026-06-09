from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from zeropark_core.database import get_db_session
from zeropark_core.models_db import User, Workflow, ChatSession
from zeropark_gateway.auth import get_current_admin_user

# Enforce that all routes in this router require admin privileges
admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)]
)

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    provider: str
    role: str
    is_active: bool

class RoleUpdateRequest(BaseModel):
    role: str

class StatsResponse(BaseModel):
    total_users: int
    local_users: int
    google_users: int
    admin_users: int
    total_workflows: int
    total_chats: int

@admin_router.get("/users", response_model=List[UserResponse])
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session)
):
    stmt = select(User).offset(skip).limit(limit)
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            provider=u.provider,
            role=u.role,
            is_active=u.is_active
        )
        for u in users
    ]

@admin_router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    body: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db_session)
):
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'user'.")
        
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    user.role = body.role
    await db.commit()
    await db.refresh(user)
    
    return {"message": f"User role updated to {user.role}"}

@admin_router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db_session)):
    # Calculate simple stats for dashboard
    total_result = await db.execute(select(func.count(User.id)))
    total_users = total_result.scalar() or 0
    
    local_result = await db.execute(select(func.count(User.id)).where(User.provider == "local"))
    local_users = local_result.scalar() or 0
    
    google_result = await db.execute(select(func.count(User.id)).where(User.provider == "google"))
    google_users = google_result.scalar() or 0
    
    admin_result = await db.execute(select(func.count(User.id)).where(User.role == "admin"))
    admin_users = admin_result.scalar() or 0
    
    workflow_result = await db.execute(select(func.count(Workflow.id)))
    total_workflows = workflow_result.scalar() or 0
    
    chat_result = await db.execute(select(func.count(ChatSession.id)))
    total_chats = chat_result.scalar() or 0
    
    return StatsResponse(
        total_users=total_users,
        local_users=local_users,
        google_users=google_users,
        admin_users=admin_users,
        total_workflows=total_workflows,
        total_chats=total_chats
    )

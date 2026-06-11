"""RAG collections: logical knowledge bases with role-based read access.

Answering "where does an upload go and who can search it":
  * Every upload targets ONE collection (default: the auto-created 'default').
  * A collection declares which roles may READ it (e.g. ["admin"] for an
    HR-only KB, ["user","admin"] for company-wide docs).
  * Queries never trust the client: the gateway computes the caller's
    readable collection ids from the DB and passes them to the engine,
    which enforces them as a Qdrant payload filter.
  * Creating/deleting collections is admin-only. Uploads are allowed into
    any collection the caller can read (admins anywhere).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from zeropark_core.database import AsyncSessionLocal
from zeropark_core.models_db import RagCollection

from zeropark_gateway.auth import get_current_user, get_current_admin_user

knowledge_router = APIRouter(prefix="/api/v1/rag/collections", tags=["rag"])

DEFAULT_COLLECTION_ID = "default"


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    allowed_roles: list[str] = Field(default_factory=lambda: ["user", "admin"])


def _to_dict(c: RagCollection) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "allowed_roles": json.loads(c.allowed_roles) if c.allowed_roles else [],
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def ensure_default_collection() -> None:
    """The zero-config path: uploads with no collection land in 'default',
    which every role can read."""
    async with AsyncSessionLocal() as session:
        if await session.get(RagCollection, DEFAULT_COLLECTION_ID) is None:
            session.add(
                RagCollection(
                    id=DEFAULT_COLLECTION_ID,
                    name="Default",
                    description="기본 지식 컬렉션 (모든 사용자 조회 가능)",
                    allowed_roles=json.dumps(["user", "admin"]),
                )
            )
            await session.commit()


async def readable_collection_ids(role: str) -> list[str]:
    """Collection ids the given role may READ. Admins read everything."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(RagCollection))
        collections = rows.scalars().all()
    if role == "admin":
        return [c.id for c in collections]
    return [
        c.id
        for c in collections
        if role in (json.loads(c.allowed_roles) if c.allowed_roles else [])
    ]


async def can_read_collection(role: str, collection_id: str) -> bool:
    return collection_id in await readable_collection_ids(role)


@knowledge_router.get("")
async def list_collections(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Users see only collections they can read; admins see all."""
    await ensure_default_collection()
    role = current_user.get("role", "user")
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(RagCollection).order_by(RagCollection.created_at))
        collections = rows.scalars().all()
    visible = [
        c for c in collections
        if role == "admin" or role in (json.loads(c.allowed_roles) if c.allowed_roles else [])
    ]
    return {"collections": [_to_dict(c) for c in visible]}


@knowledge_router.post("")
async def create_collection(
    body: CollectionCreate, admin: dict = Depends(get_current_admin_user)
) -> dict[str, Any]:
    collection = RagCollection(
        name=body.name,
        description=body.description,
        allowed_roles=json.dumps(body.allowed_roles, ensure_ascii=False),
        created_by=admin.get("user_id"),
    )
    async with AsyncSessionLocal() as session:
        session.add(collection)
        await session.commit()
        await session.refresh(collection)
    return _to_dict(collection)


@knowledge_router.delete("/{collection_id}")
async def delete_collection(
    collection_id: str, admin: dict = Depends(get_current_admin_user)
) -> dict[str, str]:
    if collection_id == DEFAULT_COLLECTION_ID:
        raise HTTPException(status_code=400, detail="The default collection cannot be deleted.")
    async with AsyncSessionLocal() as session:
        collection = await session.get(RagCollection, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Collection not found")
        await session.delete(collection)
        await session.commit()
    # Note: vectors tagged with this collection_id become unreachable (filtered
    # out for everyone). A vacuum job can purge them from Qdrant later.
    return {"status": "deleted"}

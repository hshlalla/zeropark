"""Server-side app (agent) registry.

The permission model the product sells:
  * ADMIN  — builds agents (name + mode + system prompt + default params),
             publishes/unpublishes, edits, deletes.
  * USER   — sees published agents and uses them. Nothing else.

This replaces the old per-browser localStorage list, so an agent an admin
builds is immediately visible to every user of the deployment.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from zeropark_core.database import AsyncSessionLocal
from zeropark_core.models_db import App

from zeropark_gateway.auth import get_current_user, get_current_admin_user

apps_router = APIRouter(prefix="/api/v1/apps", tags=["apps"])


class AppCreate(BaseModel):
    name: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    description: str | None = None
    system_prompt: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    published: bool = True


class AppUpdate(BaseModel):
    name: str | None = None
    mode: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    params: dict[str, Any] | None = None
    published: bool | None = None


def _app_to_dict(app: App) -> dict[str, Any]:
    return {
        "id": app.id,
        "name": app.name,
        "mode": app.mode,
        "description": app.description,
        "system_prompt": app.system_prompt,
        "params": json.loads(app.params) if app.params else {},
        "published": bool(app.published),
        "created_by": app.created_by,
        "created_at": app.created_at.isoformat() if app.created_at else None,
    }


class EnhancePromptRequest(BaseModel):
    intent: str = Field(min_length=1)


@apps_router.post("/enhance-prompt")
async def enhance_prompt(body: EnhancePromptRequest, admin: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    """Turn a one-line intent into a production-grade system prompt
    (role, constraints, tone, output format) — dify-style prompt generator."""
    from zeropark_core import ZeroparkSettings
    from zeropark_core.llm import ChatMessage, create_llm_client

    settings = ZeroparkSettings()
    if not settings.llm.api_key:
        raise HTTPException(status_code=503, detail="LLM is not configured.")
    client = create_llm_client(settings.llm.provider, settings.llm.api_key, settings.llm.base_url, settings.llm.use_local_embeddings)
    response = await client.achat_completion(
        [
            ChatMessage(
                role="system",
                content=(
                    "You write production system prompts for AI agents. Given the admin's "
                    "one-line intent, produce a complete system prompt with: 역할(role), "
                    "행동 규칙/제약(constraints), 말투(tone), 출력 형식(output format), "
                    "그리고 모르는 것은 모른다고 답하라는 안전 규칙. Write the prompt in the "
                    "same language as the intent. Conversation variables may be referenced "
                    "as {{variable_key}} placeholders if the intent mentions user inputs. "
                    "Return ONLY the system prompt text, no commentary."
                ),
            ),
            ChatMessage(role="user", content=body.intent),
        ],
        model=settings.llm.model or "gpt-4o-mini",
    )
    return {"prompt": response.content.strip()}


@apps_router.get("")
async def list_apps(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Users see published apps; admins also see drafts."""
    async with AsyncSessionLocal() as session:
        query = select(App).order_by(App.created_at.desc())
        if current_user.get("role") != "admin":
            query = query.where(App.published == True)  # noqa: E712
        rows = await session.execute(query)
        return {"apps": [_app_to_dict(a) for a in rows.scalars().all()]}


@apps_router.get("/{app_id}")
async def get_app(app_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        app = await session.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    if not app.published and current_user.get("role") != "admin":
        raise HTTPException(status_code=404, detail="App not found")
    return _app_to_dict(app)


@apps_router.post("")
async def create_app(body: AppCreate, admin: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    app = App(
        name=body.name,
        mode=body.mode,
        description=body.description,
        system_prompt=body.system_prompt,
        params=json.dumps(body.params, ensure_ascii=False),
        published=body.published,
        created_by=admin.get("user_id"),
    )
    async with AsyncSessionLocal() as session:
        session.add(app)
        await session.commit()
        await session.refresh(app)
    return _app_to_dict(app)


@apps_router.patch("/{app_id}")
async def update_app(app_id: str, body: AppUpdate, admin: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        app = await session.get(App, app_id)
        if app is None:
            raise HTTPException(status_code=404, detail="App not found")
        if body.name is not None:
            app.name = body.name
        if body.mode is not None:
            app.mode = body.mode
        if body.description is not None:
            app.description = body.description
        if body.system_prompt is not None:
            app.system_prompt = body.system_prompt
        if body.params is not None:
            app.params = json.dumps(body.params, ensure_ascii=False)
        if body.published is not None:
            app.published = body.published
        await session.commit()
        await session.refresh(app)
    return _app_to_dict(app)


@apps_router.delete("/{app_id}")
async def delete_app(app_id: str, admin: dict = Depends(get_current_admin_user)) -> dict[str, str]:
    async with AsyncSessionLocal() as session:
        app = await session.get(App, app_id)
        if app is None:
            raise HTTPException(status_code=404, detail="App not found")
        await session.delete(app)
        await session.commit()
    return {"status": "deleted"}

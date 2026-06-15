"""Conversation (chat session) management — Dify-style server-side memory.

Each agent chat runs inside a session. The gateway:
  1. loads the session's recent messages and injects them as `params.history`
     before the engine runs (so the model sees the conversation), and
  2. persists the new user/assistant turns after the run.

Sessions belong to the user who created them; users only ever see their own.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from zeropark_core.cache import redis_cache
from zeropark_core.database import AsyncSessionLocal
from zeropark_core.models_db import ChatMessage as ChatMessageRow
from zeropark_core.models_db import ChatSession, MessageFeedback

from zeropark_gateway.auth import get_current_admin_user, get_current_user

conversations_router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

HISTORY_WINDOW = 20      # turns injected into the model verbatim
SUMMARY_TRIGGER = 30     # start rolling summaries once a session exceeds this
SUMMARY_EVERY = 10       # re-summarize every N new messages after the trigger


class ConversationCreate(BaseModel):
    app_id: str | None = None
    title: str | None = None


class VariablesUpdate(BaseModel):
    values: dict[str, Any]


# ------------------------------------------------------- rolling summary

async def _default_summarize(existing_summary: str, turns: list[dict[str, str]]) -> str:
    """LLM pass that folds old turns into a compact running summary."""
    from zeropark_core import ZeroparkSettings
    from zeropark_core.llm import ChatMessage, create_llm_client

    settings = ZeroparkSettings()
    if not settings.llm.api_key:
        return existing_summary  # no LLM configured — keep whatever we had
    client = create_llm_client(settings.llm.provider, settings.llm.api_key, settings.llm.base_url)
    transcript = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
    response = await client.achat_completion(
        [
            ChatMessage(
                role="system",
                content=(
                    "You maintain a running summary of a conversation. Merge the existing "
                    "summary with the new turns into ONE concise summary (max ~200 words). "
                    "Keep concrete facts the user stated (names, numbers, preferences, "
                    "decisions). Write in the conversation's language."
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Existing summary:\n{existing_summary or '(none)'}\n\nNew turns:\n{transcript}",
            ),
        ],
        model=settings.llm.model or "gpt-4o-mini",
    )
    return response.content or existing_summary


# injectable for tests
summarize_fn: Callable[[str, list[dict[str, str]]], Awaitable[str]] = _default_summarize


async def _update_summary(session_id: str) -> None:
    """Fold turns older than the recent window into session.summary."""
    try:
        async with AsyncSessionLocal() as db:
            session = await db.get(ChatSession, session_id)
            if session is None:
                return
            rows = await db.execute(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == session_id)
                .order_by(ChatMessageRow.created_at)
            )
            messages = list(rows.scalars().all())
        old = messages[:-HISTORY_WINDOW]
        if not old:
            return
        turns = [{"role": m.role, "content": m.content} for m in old]
        new_summary = await summarize_fn(getattr(session, "summary", None) or "", turns)
        if not new_summary:
            return
        async with AsyncSessionLocal() as db:
            session = await db.get(ChatSession, session_id)
            if session is not None:
                session.summary = new_summary
                await db.commit()
    except Exception as exc:  # summarization must never break the chat itself
        print(f"Warning: conversation summary update failed: {exc}")


# ------------------------------------------------------------------ helpers
# (used by main.py task endpoints, not only by this router)

def _history_cache_key(session_id: str) -> str:
    return f"conv_history:{session_id}"


async def load_history(session_id: str, user_id: str | None) -> list[dict[str, str]]:
    """Recent turns of a session as chat-engine history. Raises 404/403.

    Cache-aside via Redis (Phase 21 infra): hot conversations are served from
    cache; the ownership check always goes to the DB so access control is
    never decided by a cache entry.
    """
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if user_id is not None and session.user_id not in (None, user_id):
            raise HTTPException(status_code=403, detail="Not your conversation")

        cached = redis_cache.get(_history_cache_key(session_id))
        if isinstance(cached, list):
            return cached[-HISTORY_WINDOW:]

        rows = await db.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.session_id == session_id)
            .order_by(ChatMessageRow.created_at)
        )
        messages = list(rows.scalars().all())[-HISTORY_WINDOW:]  # most recent turns
    history = [{"role": m.role, "content": m.content} for m in messages]
    redis_cache.set(_history_cache_key(session_id), history, ttl_seconds=86400)
    return history


async def apply_session_context(
    params: dict[str, Any], session_id: str, user_id: str | None
) -> dict[str, Any]:
    """Inject everything a session carries into the task params (server-side):

      * rolling summary (long-term memory) as a leading system history entry
      * recent turns as `params.history`
      * conversation variables: `{{key}}` substitution in `params.system`
        plus an explicit context block so the model always sees them
    """
    history = await load_history(session_id, user_id)  # also runs the auth check

    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
    summary = getattr(session, "summary", None) if session else None
    variables: dict[str, Any] = {}
    if session and getattr(session, "variables", None):
        try:
            variables = json.loads(session.variables)
        except json.JSONDecodeError:
            variables = {}

    context_entries: list[dict[str, str]] = []
    if summary:
        context_entries.append(
            {"role": "system", "content": f"Summary of the earlier conversation:\n{summary}"}
        )
    if variables:
        rendered = "\n".join(f"- {k}: {v}" for k, v in variables.items())
        context_entries.append(
            {"role": "system", "content": f"User-provided conversation variables:\n{rendered}"}
        )
        if isinstance(params.get("system"), str):
            system_text = params["system"]
            for key, value in variables.items():
                system_text = system_text.replace(f"{{{{{key}}}}}", str(value))
            params["system"] = system_text

    params["history"] = context_entries + history
    return params


async def append_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    """Persist one user/assistant exchange and bump the session."""
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            return
        # explicit timestamps with an offset: both rows are written in one
        # transaction, so identical created_at would make ordering ambiguous
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        db.add(ChatMessageRow(session_id=session_id, role="user", content=user_text, created_at=now))
        if assistant_text:
            db.add(
                ChatMessageRow(
                    session_id=session_id, role="assistant", content=assistant_text,
                    created_at=now + timedelta(milliseconds=1),
                )
            )
        if not session.title:
            session.title = user_text[:60]
        await db.commit()

        count = (
            await db.execute(
                select(func.count(ChatMessageRow.id)).where(
                    ChatMessageRow.session_id == session_id
                )
            )
        ).scalar() or 0
    # new turns invalidate the cached history (cache-aside write path)
    redis_cache.delete(_history_cache_key(session_id))

    # long conversations get a rolling summary, computed off the request path
    if count >= SUMMARY_TRIGGER and count % SUMMARY_EVERY < 2:
        asyncio.create_task(_update_summary(session_id))


# ---------------------------------------------------------------- endpoints

@conversations_router.post("")
async def create_conversation(
    body: ConversationCreate, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    session = ChatSession(
        user_id=current_user.get("user_id"),
        app_id=body.app_id,
        title=body.title,
    )
    async with AsyncSessionLocal() as db:
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return {"id": session.id, "app_id": session.app_id, "title": session.title}


@conversations_router.get("")
async def list_conversations(
    app_id: str | None = None, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        query = (
            select(ChatSession)
            .where(ChatSession.user_id == current_user.get("user_id"))
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
        if app_id:
            query = query.where(ChatSession.app_id == app_id)
        rows = await db.execute(query)
        sessions = rows.scalars().all()
    return {
        "conversations": [
            {
                "id": s.id,
                "app_id": s.app_id,
                "title": s.title or "New conversation",
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    }


@conversations_router.patch("/{session_id}/variables")
async def set_variables(
    session_id: str, body: VariablesUpdate, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """Store the values the user entered in the agent's start form."""
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if session.user_id not in (None, current_user.get("user_id")):
            raise HTTPException(status_code=403, detail="Not your conversation")
        session.variables = json.dumps(body.values, ensure_ascii=False)
        await db.commit()
    return {"status": "ok", "values": body.values}


@conversations_router.get("/{session_id}/messages")
async def get_messages(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if session.user_id not in (None, current_user.get("user_id")):
            raise HTTPException(status_code=403, detail="Not your conversation")
        rows = await db.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.session_id == session_id)
            .order_by(ChatMessageRow.created_at)
        )
        messages = rows.scalars().all()
    return {
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in messages
        ]
    }


class FeedbackCreate(BaseModel):
    rating: str  # "up" | "down"
    message_id: str | None = None
    message_content: str | None = None
    comment: str | None = None


@conversations_router.post("/{session_id}/feedback")
async def submit_feedback(
    session_id: str, body: FeedbackCreate, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if session.user_id not in (None, current_user.get("user_id")):
            raise HTTPException(status_code=403, detail="Not your conversation")
        db.add(
            MessageFeedback(
                session_id=session_id,
                message_id=body.message_id,
                user_id=current_user.get("user_id"),
                rating=body.rating,
                comment=body.comment,
                message_content=(body.message_content or "")[:2000] or None,
            )
        )
        await db.commit()
    return {"status": "ok"}


feedback_admin_router = APIRouter(prefix="/api/v1/admin/feedback", tags=["admin"])


@feedback_admin_router.get("")
async def list_feedback(
    rating: str | None = None, admin: dict = Depends(get_current_admin_user)
) -> dict[str, Any]:
    """Admin review queue: all user feedback, newest first."""
    async with AsyncSessionLocal() as db:
        query = select(MessageFeedback).order_by(MessageFeedback.created_at.desc()).limit(200)
        if rating in ("up", "down"):
            query = query.where(MessageFeedback.rating == rating)
        rows = await db.execute(query)
        items = rows.scalars().all()
    return {
        "feedback": [
            {
                "id": f.id,
                "session_id": f.session_id,
                "user_id": f.user_id,
                "rating": f.rating,
                "comment": f.comment,
                "message_content": f.message_content,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in items
        ]
    }


@conversations_router.delete("/{session_id}")
async def delete_conversation(
    session_id: str, current_user: dict = Depends(get_current_user)
) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if session.user_id not in (None, current_user.get("user_id")):
            raise HTTPException(status_code=403, detail="Not your conversation")
        await db.delete(session)
        await db.commit()
    redis_cache.delete(_history_cache_key(session_id))
    return {"status": "deleted"}

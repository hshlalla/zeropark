"""Zeropark Gateway — the framework's HTTP API.

Thin by design: it builds a registry of NATIVE engines from config, wraps it in a
Router, and exposes endpoints that delegate to them. No engine logic lives here.
"""

from __future__ import annotations

import uuid
import os
import json
import asyncio
from typing import Any, Dict

import httpx
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from zeropark_core import Capability, ProviderRegistry, Router, TaskRequest, ZeroparkSettings
from zeropark_core.database import init_db
from zeropark_core.errors import NoProviderForCapability, ProviderNotConfigured, ZeroparkError
from zeropark_core.provider import Provider
from zeropark_engines import build_registry

from zeropark_gateway.auth import get_current_user, get_current_admin_user, create_access_token, verify_password, get_password_hash
from zeropark_gateway.catalog import get_reference_catalog
from zeropark_gateway.models import (
    CrawlRequest,
    RouteRequest,
    SearchRequest,
    SlidesRequest,
    TaskCreateRequest,
)


def build_state() -> tuple[ProviderRegistry, Router]:
    settings = ZeroparkSettings()
    registry = build_registry(output_dir=settings.output_dir, search=settings.search_kwargs())
    router = Router(registry, preferences=settings.capability_preferences)
    return registry, router


def _provider_info(provider: Provider) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "capabilities": sorted(c.value for c in provider.capabilities),
        "reference": getattr(provider, "reference", ""),
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title="Zeropark Gateway",
        version="0.1.0",
        description="HTTP API for the Zeropark native AI-workspace framework.",
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    registry, router = build_state()
    app.state.registry = registry
    app.state.router = router

    @app.on_event("startup")
    async def startup_event():
        # Initialize SQLite tables
        await init_db()

    # Dummy in-memory DB for quick login test without full user registration flow
    fake_users_db = {
        "admin": {
            "username": "admin",
            "full_name": "Admin User",
            "email": "admin@example.com",
            "hashed_password": get_password_hash("secret"),
            "disabled": False,
            "role": "admin"
        },
        "user1": {
            "username": "user1",
            "full_name": "Normal User",
            "email": "user1@example.com",
            "hashed_password": get_password_hash("secret"),
            "disabled": False,
            "role": "user"
        }
    }

    @app.post("/auth/login")
    async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
        user_dict = fake_users_db.get(form_data.username)
        if not user_dict:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        if not verify_password(form_data.password, user_dict["hashed_password"]):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        
        access_token = create_access_token(
            data={"sub": user_dict["username"], "role": user_dict["role"]}
        )
        return {"access_token": access_token, "token_type": "bearer"}

    def _router(request: Request) -> Router:
        return request.app.state.router

    async def _run_capability(
        request: Request,
        capability: Capability,
        prompt: str,
        params: dict[str, Any],
        provider_id: str | None,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        router: Router = request.app.state.router
        try:
            provider = router.select(capability, prefer=provider_id)
        except NoProviderForCapability as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        task = TaskRequest(
            prompt=prompt, capability=capability, params=params, provider_id=provider_id, tenant=tenant
        )
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        try:
            result = await provider.execute(task, task_id=task_id)
        except ProviderNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Engine fetch error: {exc}") from exc
        except ZeroparkError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        registry: ProviderRegistry = request.app.state.registry
        return {
            "status": "ok",
            "providers": [_provider_info(p) for p in registry.all()],
            "capabilities": sorted(c.value for c in registry.capabilities()),
        }

    @app.get("/providers")
    def providers(request: Request) -> dict[str, Any]:
        registry: ProviderRegistry = request.app.state.registry
        return {"providers": [_provider_info(p) for p in registry.all()]}

    @app.get("/catalog")
    def catalog() -> dict[str, Any]:
        return {"references": get_reference_catalog()}

    @app.get("/modes")
    def modes(request: Request) -> dict[str, Any]:
        router = _router(request)
        return {
            "modes": {
                name: {
                    "primary": plan.primary.value,
                    "pipeline": [c.value for c in plan.pipeline],
                    "description": plan.description,
                }
                for name, plan in router.modes.items()
            }
        }

    @app.post("/route")
    def route(request: Request, body: RouteRequest) -> dict[str, Any]:
        router = _router(request)
        try:
            plan = router.plan(body.mode)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}") from exc
        resolved = router.resolve(body.mode)
        return {
            "prompt": body.prompt,
            "mode": body.mode,
            "primary": plan.primary.value,
            "resolved": {cap.value: prov.id for cap, prov in resolved.items()},
            "missing": [c.value for c in plan.pipeline if c not in resolved],
        }

    @app.post("/api/v1/tasks")
    async def create_task(request: Request, body: TaskCreateRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
        print(f"Task initiated by user {current_user['user_id']}")
        router = _router(request)
        try:
            plan = router.plan(body.mode)
        except ZeroparkError as e:
            raise HTTPException(status_code=400, detail=str(e))
            
        return {"task_id": "dummy", "plan": [c.value for c in plan.pipeline]}

    @app.get("/api/v1/admin/system-status")
    async def get_system_status(current_admin: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
        """Admin only endpoint to get system status."""
        print(f"Admin API accessed by {current_admin['user_id']}")
        return {
            "status": "healthy",
            "active_users": 42,
            "running_tasks": 3,
            "sandbox_type": "DockerSandbox"
        }

    @app.post("/search")
    async def search(request: Request, body: SearchRequest) -> dict[str, Any]:
        return await _run_capability(
            request, Capability.SEARCH, body.query, {"limit": body.limit}, body.provider_id
        )

    @app.post("/crawl")
    async def crawl(request: Request, body: CrawlRequest) -> dict[str, Any]:
        return await _run_capability(
            request, Capability.CRAWL, body.url, {"url": body.url, **body.params}, body.provider_id
        )

    @app.post("/slides")
    async def slides(request: Request, body: SlidesRequest) -> dict[str, Any]:
        params = body.model_dump(exclude={"provider_id"})
        return await _run_capability(
            request, Capability.SLIDES, body.content, params, body.provider_id
        )

    return app


app = create_app()

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
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from zeropark_core import Capability, ProviderRegistry, Router, TaskRequest, ZeroparkSettings
from zeropark_core.database import init_db
from zeropark_core.errors import NoProviderForCapability, ProviderNotConfigured, ZeroparkError
from zeropark_core.provider import Provider
from zeropark_engines import build_registry

from zeropark_gateway.auth import get_current_user, get_current_admin_user, auth_router
from zeropark_gateway.admin import admin_router
from zeropark_gateway.workflow import workflow_router
from zeropark_gateway.catalog import get_reference_catalog
from zeropark_gateway.exceptions import setup_exception_handlers
from zeropark_gateway.models import (
    CrawlRequest,
    RouteRequest,
    SearchRequest,
    SlidesRequest,
    TaskCreateRequest,
)

class RagUploadRequest(BaseModel):
    texts: list[str]

class RagQueryRequest(BaseModel):
    query: str
    provider_id: str | None = None


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
    
    setup_exception_handlers(app)
    
    registry, router = build_state()
    app.state.registry = registry
    app.state.router = router

    @app.on_event("startup")
    async def startup_event():
        # Initialize SQLite tables
        await init_db()

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(workflow_router)

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

    @app.post("/api/v1/rag/upload")
    async def rag_upload(request: Request, files: list[UploadFile] = File(...), current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
        texts = []
        for file in files:
            content = await file.read()
            # Basic text extraction (assuming .txt files for now)
            # In a real scenario, you'd use a PDF parser or similar here
            texts.append(content.decode("utf-8", errors="ignore"))
            
        params = {
            "context_texts": texts,
            "user_role": current_user["role"]
        }
        return await _run_capability(
            request, Capability.RAG, "upload_only", params, None
        )

    @app.post("/api/v1/rag/query")
    async def rag_query(request: Request, body: RagQueryRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
        params = {
            "user_role": current_user["role"]
        }
        return await _run_capability(
            request, Capability.RAG, body.query, params, body.provider_id
        )

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

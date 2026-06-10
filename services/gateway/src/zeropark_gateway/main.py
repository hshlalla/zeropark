"""Zeropark Gateway — the framework's HTTP API.

Thin by design: it builds a registry of NATIVE engines from config, wraps it in a
Router, and exposes endpoints that delegate to them. No engine logic lives here.
"""

from __future__ import annotations

import uuid
import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

import httpx
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from zeropark_core import Capability, ProviderRegistry, Router, TaskRequest, ZeroparkSettings
from zeropark_core.database import init_db
from zeropark_core.errors import NoProviderForCapability, ProviderNotConfigured, ZeroparkError
from zeropark_core.netguard import BlockedURLError, validate_public_url
from zeropark_core.provider import Provider
from zeropark_engines import build_registry

from zeropark_gateway.auth import get_current_user, get_current_admin_user, auth_router
from zeropark_gateway.admin import admin_router
from zeropark_gateway.workflow import workflow_router
from zeropark_gateway.jobs import jobs_router
from zeropark_gateway.prompt import prompt_router
from zeropark_gateway.dataset import dataset_router
from zeropark_gateway.observability import observability_router
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


def build_state() -> tuple[ProviderRegistry, Router, ZeroparkSettings]:
    settings = ZeroparkSettings()
    registry = build_registry(
        output_dir=settings.output_dir,
        search=settings.search_kwargs(),
        llm=settings.llm_kwargs(),
        features=settings.features,
    )
    router = Router(registry, preferences=settings.capability_preferences)
    return registry, router, settings


def apply_profile(app: FastAPI, profile: dict[str, Any]) -> bool:
    """Apply a control-plane profile (branding + features) to the running app.

    Returns True when something changed. A feature-flag change rebuilds the
    registry/router so engines are added/removed live — no redeploy needed.
    """
    settings: ZeroparkSettings = app.state.settings
    changed = False

    branding = profile.get("branding")
    if branding:
        merged = settings.branding.model_dump() | {
            k: v for k, v in branding.items() if v is not None
        }
        if merged != settings.branding.model_dump():
            settings.branding = type(settings.branding)(**merged)
            changed = True

    features = profile.get("features")
    if features is not None and features != settings.features:
        settings.features = features
        changed = True

    preferences = profile.get("preferences")
    if preferences is not None and preferences != settings.capability_preferences:
        settings.capability_preferences = preferences
        changed = True

    if changed:
        registry = build_registry(
            output_dir=settings.output_dir,
            search=settings.search_kwargs(),
            llm=settings.llm_kwargs(),
            features=settings.features,
        )
        app.state.registry = registry
        app.state.router = Router(registry, preferences=settings.capability_preferences)

    return changed


async def _heartbeat_loop(app: FastAPI, settings: ZeroparkSettings) -> None:
    """Report liveness/usage to the control plane if one is configured."""
    cp = settings.control_plane
    while True:
        try:
            registry: ProviderRegistry = app.state.registry
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{cp.url.rstrip('/')}/api/v1/heartbeat",
                    json={
                        "deployment_id": cp.deployment_id,
                        "license_key": cp.license_key,
                        "version": app.version,
                        "capabilities": sorted(c.value for c in registry.capabilities()),
                    },
                )
            if response.status_code == 200:
                profile = response.json().get("profile") or {}
                if profile and apply_profile(app, profile):
                    print("[Zeropark] Profile updated from control plane (hot-reload).")
        except Exception:
            pass  # control plane being down must never affect the product
        await asyncio.sleep(cp.heartbeat_interval_s)


def _provider_info(provider: Provider) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "capabilities": sorted(c.value for c in provider.capabilities),
        "reference": getattr(provider, "reference", ""),
    }


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()  # create DB tables on startup
        heartbeat_task = None
        settings: ZeroparkSettings = app.state.settings
        if settings.control_plane.url:
            heartbeat_task = asyncio.create_task(_heartbeat_loop(app, settings))
        yield
        if heartbeat_task:
            heartbeat_task.cancel()

    app = FastAPI(
        title="Zeropark Gateway",
        version="0.1.0",
        description="HTTP API for the Zeropark native AI-workspace framework.",
        lifespan=lifespan,
    )
    
    _cors_origins = [
        o.strip()
        for o in os.environ.get("ZEROPARK_CORS_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    setup_exception_handlers(app)
    
    registry, router, settings = build_state()
    app.state.registry = registry
    app.state.router = router
    app.state.settings = settings

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(workflow_router)
    app.include_router(jobs_router)
    app.include_router(prompt_router)
    app.include_router(dataset_router)
    app.include_router(observability_router)

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
        # SSRF guard: any user-supplied URL must resolve to a public address.
        # (Engines re-validate at fetch time; validating here returns a clean 400
        # instead of a failed task.) Prompt-injection defense is handled by tool
        # permissioning in the engines, not by string blacklists.
        url_param = params.get("url")
        if url_param:
            try:
                validate_public_url(str(url_param))
            except BlockedURLError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    @app.get("/api/v1/profile")
    def profile(request: Request) -> dict[str, Any]:
        """Deployment profile: branding + enabled capabilities. The web shell
        reads this at boot to white-label itself per client (Samsung, LG, ...)."""
        settings: ZeroparkSettings = request.app.state.settings
        registry: ProviderRegistry = request.app.state.registry
        return {
            "branding": settings.branding.model_dump(),
            "environment": settings.environment,
            "capabilities": sorted(c.value for c in registry.capabilities()),
            "features": settings.features,
        }

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
    async def create_task(request: Request, body: TaskCreateRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
        router = _router(request)
        try:
            plan = router.plan(body.mode)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}") from exc
            
        result = await _run_capability(
            request, plan.primary, body.prompt, body.params, body.provider_id, body.tenant
        )
        result["mode"] = body.mode
        result["initiated_by"] = current_user.get("user_id")
        return result

    @app.post("/api/v1/tasks/stream")
    async def stream_task(
        request: Request,
        body: TaskCreateRequest,
        current_user: dict = Depends(get_current_user),
    ) -> StreamingResponse:
        """Run a task and stream progress as Server-Sent Events (text/event-stream).

        Each SSE `data:` line is a RunEvent JSON: a `status` (started), optional
        engine events, one `artifact` event per output, then `done` carrying the
        full TaskResult. The web shell renders a live run timeline from these.
        """
        router = _router(request)
        try:
            plan = router.plan(body.mode)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}") from exc
        try:
            provider = router.select(plan.primary, prefer=body.provider_id)
        except NoProviderForCapability as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        task = TaskRequest(
            prompt=body.prompt,
            capability=plan.primary,
            params=body.params,
            provider_id=body.provider_id,
            tenant=body.tenant,
        )
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        async def event_source():
            def sse(payload: dict[str, Any]) -> str:
                return f"data: {json.dumps(payload, default=str)}\n\n"

            try:
                async for event in provider.stream(task, task_id=task_id):
                    yield sse(event.model_dump(mode="json"))
            except (ProviderNotConfigured, ZeroparkError) as exc:
                yield sse({"type": "error", "task_id": task_id, "message": str(exc)})
            except httpx.HTTPError as exc:
                yield sse({"type": "error", "task_id": task_id, "message": f"Engine fetch error: {exc}"})

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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

"""Zeropark Gateway — the framework's HTTP API.

Thin by design: it builds a registry of NATIVE engines from config, wraps it in a
Router, and exposes endpoints that delegate to them. No engine logic lives here.
"""

from __future__ import annotations

import uuid
import os

# Load .env into os.environ BEFORE any module reads it directly (auth.py reads
# SECRET_KEY via os.environ; pydantic-settings only covers ZEROPARK_* fields).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
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
from zeropark_gateway.apps import apps_router
from zeropark_gateway.knowledge import (
    knowledge_router,
    can_read_collection,
    ensure_default_collection,
    readable_collection_ids,
)
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
    # optionally narrow the search to one collection (must be readable)
    collection_id: str | None = None


class UsageTracker:
    """In-process usage counters, reported to the control plane on heartbeat.

    Cumulative since process start — the control plane stores the latest
    snapshot per deployment, so restarts simply reset the baseline.
    """

    def __init__(self) -> None:
        self.tasks_total = 0
        self.tasks_failed = 0
        self.tokens_total = 0
        self.by_capability: dict[str, int] = {}

    def record(self, capability: str, result: dict[str, Any] | None, *, failed: bool = False) -> None:
        self.tasks_total += 1
        if failed:
            self.tasks_failed += 1
        self.by_capability[capability] = self.by_capability.get(capability, 0) + 1
        metrics = (result or {}).get("metrics") or {}
        try:
            self.tokens_total += int(metrics.get("total_tokens", 0))
        except (TypeError, ValueError):
            pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "tasks_total": self.tasks_total,
            "tasks_failed": self.tasks_failed,
            "tokens_total": self.tokens_total,
            "by_capability": dict(self.by_capability),
        }


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
                        "usage": app.state.usage.snapshot(),
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
        for o in os.environ.get(
            "ZEROPARK_CORS_ORIGINS",
            # local web shells: vite dev (5173), CRA (3000), docker web (80),
            # plus 127.0.0.1 variants (the browser treats them as a different origin)
            "http://localhost:5173,http://localhost:3000,http://localhost,"
            "http://127.0.0.1:5173,http://127.0.0.1:3000,http://127.0.0.1",
        ).split(",")
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
    
    # generated artifacts (pages, podcasts, decks) are served statically so the
    # UI can link to them: /artifacts/<filename>
    from fastapi.staticfiles import StaticFiles
    _settings_for_static = ZeroparkSettings()
    os.makedirs(_settings_for_static.output_dir, exist_ok=True)
    app.mount("/artifacts", StaticFiles(directory=_settings_for_static.output_dir), name="artifacts")

    registry, router, settings = build_state()
    app.state.registry = registry
    app.state.router = router
    app.state.settings = settings
    app.state.usage = UsageTracker()

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(workflow_router)
    app.include_router(jobs_router)
    app.include_router(apps_router)
    app.include_router(knowledge_router)
    app.include_router(prompt_router)
    app.include_router(dataset_router)
    app.include_router(observability_router)

    from zeropark_gateway.conversations import conversations_router
    app.include_router(conversations_router)
    from zeropark_gateway.conversations import feedback_admin_router
    app.include_router(feedback_admin_router)

    def _router(request: Request) -> Router:
        return request.app.state.router

    async def _secure_rag_params(params: dict[str, Any], role: str) -> dict[str, Any]:
        """Server-side RAG access control for EVERY task path.

        The caller's readable collections come from the DB; if the app/task
        pinned specific collections (params.collection_ids), they are
        intersected with that set — a client can narrow, never widen, access.
        """
        await ensure_default_collection()
        allowed = await readable_collection_ids(role)
        pinned = params.get("collection_ids") or params.get("allowed_collection_ids")
        if pinned:
            allowed = [c for c in pinned if c in allowed]
        params["allowed_collection_ids"] = allowed
        return params

    async def _run_capability(
        request: Request,
        capability: Capability,
        prompt: str,
        params: dict[str, Any],
        provider_id: str | None,
        tenant: str | None = None,
        user_role: str | None = None,
    ) -> dict[str, Any]:
        settings: ZeroparkSettings = request.app.state.settings
        
        # --- Semantic Cache Check ---
        from zeropark_core.semantic_cache import semantic_cache
        from zeropark_core.llm import create_llm_client
        llm_client = None
        query_emb = None
        
        if settings.semantic_cache_enabled and capability in (Capability.CHAT, Capability.RAG) and prompt and prompt != "upload_only":
            try:
                llm_client = create_llm_client(
                    provider=settings.llm.provider,
                    api_key=settings.llm.api_key,
                    base_url=settings.llm.base_url,
                    use_local_embeddings=settings.llm.use_local_embeddings
                )
                query_emb = llm_client.create_embeddings([prompt])[0]
                cached_answer = semantic_cache.similarity_search(query_emb)
                if cached_answer:
                    # Return mocked TaskResult
                    from zeropark_core import TaskStatus, Artifact
                    return {
                        "task_id": f"task_{uuid.uuid4().hex[:12]}",
                        "status": TaskStatus.SUCCEEDED.value,
                        "capability": capability.value,
                        "provider_id": "semantic_cache",
                        "artifacts": [
                            {
                                "id": f"art_{uuid.uuid4().hex[:12]}",
                                "kind": "message",
                                "title": "Cached Answer",
                                "inline": cached_answer,
                                "metadata": {"cached": True}
                            }
                        ],
                        "metrics": {"cached": True}
                    }
            except Exception as e:
                print(f"Semantic Cache check failed: {e}")
        # ---------------------------
        needs_rag_clipping = capability == Capability.RAG or (
            capability == Capability.CHAT and params.get("collection_ids")
        )
        if needs_rag_clipping and user_role is not None:
            params = await _secure_rag_params(params, user_role)
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
        usage: UsageTracker = request.app.state.usage
        try:
            result = await provider.execute(task, task_id=task_id)
        except ProviderNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            usage.record(capability.value, None, failed=True)
            raise HTTPException(status_code=502, detail=f"Engine fetch error: {exc}") from exc
        except ZeroparkError as exc:
            usage.record(capability.value, None, failed=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = result.model_dump(mode="json")
        usage.record(capability.value, payload, failed=result.status.value == "failed")
        
        # --- Semantic Cache Save ---
        if settings.semantic_cache_enabled and query_emb and result.status.value == "succeeded":
            inline = next(
                (a.get("inline") for a in payload.get("artifacts", [])
                 if isinstance(a.get("inline"), str) and a.get("inline")),
                None,
            )
            if inline:
                # Fire and forget
                import asyncio
                asyncio.get_event_loop().run_in_executor(
                    None, semantic_cache.set_cache, query_emb, inline
                )
        # ---------------------------
        
        return payload

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
            # models admins may assign per agent (never includes the api key)
            "models": settings.llm.model_choices(),
        }

    @app.get("/api/v1/usage")
    def usage_snapshot(request: Request) -> dict[str, Any]:
        """Cumulative usage counters for this process (also sent on heartbeat)."""
        return request.app.state.usage.snapshot()

    @app.get("/catalog")
    def catalog() -> dict[str, Any]:
        return {"references": get_reference_catalog()}

    @app.get("/modes")
    def modes(request: Request) -> dict[str, Any]:
        router = _router(request)
        registry: ProviderRegistry = request.app.state.registry
        served = registry.capabilities()
        return {
            "modes": {
                name: {
                    "primary": plan.primary.value,
                    "pipeline": [c.value for c in plan.pipeline],
                    "description": plan.description,
                    # whether THIS deployment has an engine for the mode's
                    # primary capability — the UI greys out unavailable modes
                    "available": plan.primary in served,
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
            
        task_params = dict(body.params or {})
        session_id = body.session_id or task_params.get("session_id")
        if session_id:
            from zeropark_gateway.conversations import apply_session_context
            task_params = await apply_session_context(
                task_params, session_id, current_user.get("user_id")
            )

        result = await _run_capability(
            request, plan.primary, body.prompt, task_params, body.provider_id, body.tenant,
            user_role=current_user.get("role", "user"),
        )
        result["mode"] = body.mode
        result["initiated_by"] = current_user.get("user_id")

        if session_id:
            from zeropark_gateway.conversations import append_turn
            inline = next(
                (a.get("inline") for a in result.get("artifacts", [])
                 if isinstance(a.get("inline"), str) and a.get("inline")),
                "",
            )
            await append_turn(session_id, body.prompt, inline)
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

        task_params = dict(body.params or {})
        if plan.primary == Capability.RAG or (
            plan.primary == Capability.CHAT and task_params.get("collection_ids")
        ):
            task_params = await _secure_rag_params(
                task_params, current_user.get("role", "user")
            )

        session_id = body.session_id or task_params.get("session_id")
        if session_id:
            from zeropark_gateway.conversations import apply_session_context
            try:
                task_params = await apply_session_context(
                    task_params, session_id, current_user.get("user_id")
                )
            except Exception:
                pass

        task = TaskRequest(
            prompt=body.prompt,
            capability=plan.primary,
            params=task_params,
            provider_id=body.provider_id,
            tenant=body.tenant,
        )
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        
        # --- Semantic Cache Check ---
        settings: ZeroparkSettings = request.app.state.settings
        from zeropark_core.semantic_cache import semantic_cache
        from zeropark_core.llm import create_llm_client
        llm_client = None
        query_emb = None
        cached_answer = None
        
        if settings.semantic_cache_enabled and plan.primary in (Capability.CHAT, Capability.RAG) and body.prompt and body.prompt != "upload_only":
            try:
                llm_client = create_llm_client(
                    provider=settings.llm.provider,
                    api_key=settings.llm.api_key,
                    base_url=settings.llm.base_url,
                    use_local_embeddings=settings.llm.use_local_embeddings
                )
                query_emb = llm_client.create_embeddings([body.prompt])[0]
                cached_answer = semantic_cache.similarity_search(query_emb)
            except Exception as e:
                print(f"Semantic Cache check failed in stream: {e}")
        # ---------------------------

        async def event_source():
            def sse(payload: dict[str, Any]) -> str:
                return f"data: {json.dumps(payload, default=str)}\n\n"

            ai_content = ""
            try:
                if cached_answer:
                    # Stream the cached answer
                    ai_content = cached_answer
                    from zeropark_core import RunEvent, TaskStatus
                    yield sse(RunEvent(task_id=task_id, type="status", status=TaskStatus.STARTED).model_dump(mode="json"))
                    yield sse(RunEvent(
                        task_id=task_id,
                        type="artifact",
                        data={"artifact": {
                            "id": f"art_{uuid.uuid4().hex[:12]}",
                            "kind": "message",
                            "title": "Cached Answer",
                            "inline": cached_answer,
                            "metadata": {"cached": True}
                        }}
                    ).model_dump(mode="json"))
                    yield sse(RunEvent(task_id=task_id, type="done", status=TaskStatus.SUCCEEDED).model_dump(mode="json"))
                else:
                    async for event in provider.stream(task, task_id=task_id):
                        if event.type == "token":
                            ai_content += event.message or ""
                        elif event.type == "artifact" and not ai_content:
                            art = event.data.get("artifact", {})
                            if art.get("inline"):
                                ai_content = art["inline"]
                        yield sse(event.model_dump(mode="json"))
            except (ProviderNotConfigured, ZeroparkError) as exc:
                yield sse({"type": "error", "task_id": task_id, "message": str(exc)})
            except httpx.HTTPError as exc:
                yield sse({"type": "error", "task_id": task_id, "message": f"Engine fetch error: {exc}"})
            finally:
                if session_id and ai_content:
                    from zeropark_gateway.conversations import append_turn
                    await append_turn(session_id, body.prompt, ai_content)
                
                # --- Semantic Cache Save ---
                if not cached_answer and settings.semantic_cache_enabled and query_emb and ai_content:
                    import asyncio
                    asyncio.get_event_loop().run_in_executor(
                        None, semantic_cache.set_cache, query_emb, ai_content
                    )
                # ---------------------------

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/rag/upload")
    async def rag_upload(
        request: Request,
        files: list[UploadFile] = File(...),
        collection_id: str = "default",
        current_user: dict = Depends(get_current_user),
    ) -> dict[str, Any]:
        await ensure_default_collection()
        role = current_user.get("role", "user")
        # Upload permission = read permission on the target collection
        # (admins can read every collection, so they can upload anywhere).
        if not await can_read_collection(role, collection_id):
            raise HTTPException(
                status_code=403,
                detail=f"You cannot upload into collection '{collection_id}'.",
            )

        from zeropark_gateway.knowledge import extract_text

        texts = []
        for file in files:
            content = await file.read()
            try:
                text = extract_text(file.filename or "", content)
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{file.filename}' 텍스트 추출 실패: {exc}",
                ) from exc
            if text.strip():
                texts.append(text)
        if not texts:
            raise HTTPException(status_code=400, detail="No extractable text in the uploaded files.")

        params = {
            "context_texts": texts,
            "collection_id": collection_id,
            "allowed_collection_ids": [],  # upload-only: no retrieval needed
        }
        return await _run_capability(
            request, Capability.RAG, "upload_only", params, None
        )

    @app.post("/api/v1/rag/query")
    async def rag_query(request: Request, body: RagQueryRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
        await ensure_default_collection()
        role = current_user.get("role", "user")
        # The readable set is computed server-side from the DB — the client
        # cannot widen its own access by sending collection ids.
        allowed = await readable_collection_ids(role)
        if body.collection_id is not None:
            if body.collection_id not in allowed:
                raise HTTPException(status_code=403, detail="No access to this collection.")
            allowed = [body.collection_id]
        params = {"allowed_collection_ids": allowed}
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

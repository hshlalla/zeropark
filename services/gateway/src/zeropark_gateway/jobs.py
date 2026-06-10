"""Background jobs: persisted, long-running agent tasks with live SSE progress.

Deep-research / super-agent runs take minutes, so they must not be tied to a
single request/response cycle. A job is persisted to the DB (survives client
disconnects and server restarts report a terminal/orphaned state), executed on
an asyncio background task, and exposes:

  POST /api/v1/jobs               create + start
  GET  /api/v1/jobs               list my jobs
  GET  /api/v1/jobs/{id}          poll status/result
  GET  /api/v1/jobs/{id}/events   SSE: replay buffered events, then live ones
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from zeropark_core import Capability, RunEvent, TaskRequest
from zeropark_core.database import AsyncSessionLocal
from zeropark_core.errors import NoProviderForCapability
from zeropark_core.models_db import Job

from zeropark_gateway.auth import get_current_user

jobs_router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    mode: str
    prompt: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    provider_id: str | None = None


class _LiveJob:
    """In-memory event fan-out for one running job."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.subscribers: list[asyncio.Queue] = []
        self.done = asyncio.Event()

    def publish(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        for q in self.subscribers:
            q.put_nowait(event)

    def finish(self) -> None:
        self.done.set()
        for q in self.subscribers:
            q.put_nowait(None)


class JobManager:
    def __init__(self) -> None:
        self.live: dict[str, _LiveJob] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    async def _set_status(self, job_id: str, **fields: Any) -> None:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            await session.commit()

    async def start(self, app_router, capability: Capability, job_id: str, body: JobCreateRequest) -> None:
        live = _LiveJob()
        self.live[job_id] = live

        async def run() -> None:
            await self._set_status(job_id, status="running")
            terminal_status = "failed"
            result_json: str | None = None
            error: str | None = None
            try:
                provider = app_router.select(capability, prefer=body.provider_id)
                task = TaskRequest(
                    prompt=body.prompt,
                    capability=capability,
                    params=body.params,
                    provider_id=body.provider_id,
                )
                async for event in provider.stream(task, task_id=f"job_{job_id}"):
                    payload = event.model_dump(mode="json")
                    live.publish(payload)
                    if event.type == "done":
                        result_json = json.dumps(payload.get("data", {}).get("result"), default=str)
                        status_value = payload.get("data", {}).get("status", "succeeded")
                        terminal_status = status_value
                    elif event.type == "error":
                        error = event.message
            except NoProviderForCapability as exc:
                error = str(exc)
                live.publish({"type": "error", "task_id": f"job_{job_id}", "message": error})
            except Exception as exc:  # persist the failure instead of losing it
                error = str(exc)
                live.publish({"type": "error", "task_id": f"job_{job_id}", "message": error})
            finally:
                await self._set_status(
                    job_id,
                    status=terminal_status if error is None else "failed",
                    result=result_json,
                    error=error,
                )
                live.finish()
                self.tasks.pop(job_id, None)

        self.tasks[job_id] = asyncio.create_task(run())


def _job_to_dict(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "mode": job.mode,
        "prompt": job.prompt,
        "params": json.loads(job.params) if job.params else {},
        "status": job.status,
        "result": json.loads(job.result) if job.result else None,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def _manager(request: Request) -> JobManager:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        manager = JobManager()
        request.app.state.job_manager = manager
    return manager


@jobs_router.post("")
async def create_job(
    request: Request,
    body: JobCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    router = request.app.state.router
    try:
        plan = router.plan(body.mode)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}") from exc
    try:
        router.select(plan.primary, prefer=body.provider_id)
    except NoProviderForCapability as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    async with AsyncSessionLocal() as session:
        session.add(
            Job(
                id=job_id,
                user_id=current_user.get("user_id"),
                mode=body.mode,
                prompt=body.prompt,
                params=json.dumps(body.params, default=str),
                status="pending",
            )
        )
        await session.commit()

    await _manager(request).start(router, plan.primary, job_id, body)
    return {"job_id": job_id, "status": "pending"}


@jobs_router.get("")
async def list_jobs(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Job)
            .where(Job.user_id == current_user.get("user_id"))
            .order_by(Job.created_at.desc())
            .limit(50)
        )
        return {"jobs": [_job_to_dict(j) for j in rows.scalars().all()]}


@jobs_router.get("/{job_id}")
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@jobs_router.get("/{job_id}/events")
async def job_events(
    request: Request,
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    manager = _manager(request)
    live = manager.live.get(job_id)

    async def event_source():
        def sse(payload: dict[str, Any]) -> str:
            return f"data: {json.dumps(payload, default=str)}\n\n"

        if live is None:
            # Job finished earlier (or never existed): replay terminal state from DB.
            async with AsyncSessionLocal() as session:
                job = await session.get(Job, job_id)
            if job is None:
                yield sse({"type": "error", "message": "Job not found"})
                return
            yield sse({"type": "done", "data": {"status": job.status, "result": json.loads(job.result) if job.result else None}})
            return

        queue: asyncio.Queue = asyncio.Queue()
        # Replay what already happened, then subscribe for live events.
        for event in list(live.events):
            yield sse(event)
        if live.done.is_set():
            return
        live.subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield sse(event)
        finally:
            if queue in live.subscribers:
                live.subscribers.remove(queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

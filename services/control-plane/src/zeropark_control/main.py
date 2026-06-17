"""Zeropark Control Plane — fleet management for client deployments.

This service runs on OUR infrastructure (never shipped to clients) and manages
every Zeropark deployment we operate for customers (Samsung, LG, ...):

  * deployment registry: who has what, where, on which version
  * license keys: each product deployment authenticates its heartbeat with one
  * liveness: products send POST /api/v1/heartbeat; a deployment is `online`
    if it reported within 3x its heartbeat interval
  * profile management: the branding/feature-flag JSON a deployment runs with

The product gateway reports here when ZEROPARK_CONTROL_PLANE__URL is set; the
control plane being down never affects a product deployment.
"""

from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, String, event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("CONTROL_PLANE_DATABASE_URL", "sqlite+aiosqlite:///./controlplane.db")
ONLINE_GRACE_FACTOR = 3
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)

if _IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    client_name = Column(String, nullable=False, index=True)   # "Samsung", "LG", ...
    base_url = Column(String, nullable=True)                    # where the product runs
    license_key = Column(String, nullable=False, unique=True, index=True)
    profile = Column(String, nullable=True)                     # JSON: branding + features
    version = Column(String, nullable=True)                     # last reported product version
    capabilities = Column(String, nullable=True)                # JSON list, last reported
    usage = Column(String, nullable=True)                       # JSON usage snapshot, last reported
    heartbeat_interval_s = Column(String, default="60")
    last_heartbeat = Column(DateTime, nullable=True)
    is_active = Column(String, default="true")                  # license switch
    created_at = Column(DateTime, default=datetime.utcnow)


class UsageRecord(Base):
    """Time-series of usage snapshots, one row per heartbeat — the data
    monthly billing and trend charts are built from."""
    __tablename__ = "usage_records"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    deployment_id = Column(String, index=True, nullable=False)
    usage = Column(String, nullable=False)  # JSON snapshot
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ----------------------------------------------------------------- schemas

class DeploymentCreate(BaseModel):
    name: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    base_url: str | None = None
    profile: dict[str, Any] = Field(default_factory=dict)
    heartbeat_interval_s: int = 60


class DeploymentUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    profile: dict[str, Any] | None = None
    is_active: bool | None = None


class HeartbeatRequest(BaseModel):
    deployment_id: str
    license_key: str
    version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    usage: dict[str, Any] | None = None


# -------------------------------------------------------------------- auth

def require_admin(x_admin_token: str = Header(default="")) -> None:
    expected = os.environ.get("ZEROPARK_CP_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Control plane is not configured: set ZEROPARK_CP_ADMIN_TOKEN.",
        )
    if not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


# --------------------------------------------------------------------- app

def _deployment_to_dict(d: Deployment) -> dict[str, Any]:
    import json

    interval = int(d.heartbeat_interval_s or "60")
    online = (
        d.last_heartbeat is not None
        and datetime.utcnow() - d.last_heartbeat < timedelta(seconds=interval * ONLINE_GRACE_FACTOR)
    )
    return {
        "id": d.id,
        "name": d.name,
        "client_name": d.client_name,
        "base_url": d.base_url,
        "license_key": d.license_key,
        "profile": json.loads(d.profile) if d.profile else {},
        "version": d.version,
        "capabilities": json.loads(d.capabilities) if d.capabilities else [],
        "usage": json.loads(d.usage) if d.usage else None,
        "is_active": d.is_active == "true",
        "online": online,
        "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


async def _offline_watcher() -> None:
    """Alert (webhook) when a deployment stops heartbeating.

    Fires once per offline transition; recovering deployments re-arm the alert.
    Configure with ZEROPARK_CP_ALERT_WEBHOOK (e.g. a Slack incoming webhook).
    """
    import asyncio
    import json

    import httpx

    webhook = os.environ.get("ZEROPARK_CP_ALERT_WEBHOOK")
    if not webhook:
        return
    alerted: set[str] = set()
    while True:
        try:
            async with AsyncSessionLocal() as session:
                rows = await session.execute(select(Deployment))
                deployments = rows.scalars().all()
            now = datetime.utcnow()
            for d in deployments:
                if d.is_active != "true" or d.last_heartbeat is None:
                    continue
                interval = int(d.heartbeat_interval_s or "60")
                offline = now - d.last_heartbeat > timedelta(seconds=interval * ONLINE_GRACE_FACTOR)
                if offline and d.id not in alerted:
                    alerted.add(d.id)
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(webhook, json={
                            "text": (
                                f"[Zeropark] 배포본 offline: {d.name} ({d.client_name}) — "
                                f"마지막 하트비트 {d.last_heartbeat.isoformat()}Z"
                            ),
                            "deployment_id": d.id,
                        })
                elif not offline:
                    alerted.discard(d.id)  # recovered — re-arm
        except Exception as exc:
            print(f"Warning: offline watcher iteration failed: {exc}")
        await asyncio.sleep(60)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        watcher = asyncio.create_task(_offline_watcher())
        yield
        watcher.cancel()

    app = FastAPI(
        title="Zeropark Control Plane",
        version="0.1.0",
        description="Fleet management for Zeropark client deployments.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        from zeropark_control.dashboard import DASHBOARD_HTML

        return HTMLResponse(DASHBOARD_HTML)

    # ------------------------------------------------- deployments (admin)

    @app.post("/api/v1/deployments", dependencies=[Depends(require_admin)])
    async def create_deployment(body: DeploymentCreate) -> dict[str, Any]:
        import json

        deployment = Deployment(
            id=uuid.uuid4().hex,
            name=body.name,
            client_name=body.client_name,
            base_url=body.base_url,
            license_key=f"zp_{secrets.token_urlsafe(32)}",
            profile=json.dumps(body.profile, ensure_ascii=False),
            heartbeat_interval_s=str(body.heartbeat_interval_s),
        )
        async with AsyncSessionLocal() as session:
            session.add(deployment)
            await session.commit()
        return _deployment_to_dict(deployment)

    @app.get("/api/v1/deployments", dependencies=[Depends(require_admin)])
    async def list_deployments(client: str | None = None) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            query = select(Deployment).order_by(Deployment.created_at.desc())
            if client:
                query = query.where(Deployment.client_name == client)
            rows = await session.execute(query)
            return {"deployments": [_deployment_to_dict(d) for d in rows.scalars().all()]}

    @app.get("/api/v1/deployments/{deployment_id}", dependencies=[Depends(require_admin)])
    async def get_deployment(deployment_id: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            deployment = await session.get(Deployment, deployment_id)
        if deployment is None:
            raise HTTPException(status_code=404, detail="Deployment not found")
        return _deployment_to_dict(deployment)

    @app.patch("/api/v1/deployments/{deployment_id}", dependencies=[Depends(require_admin)])
    async def update_deployment(deployment_id: str, body: DeploymentUpdate) -> dict[str, Any]:
        import json

        async with AsyncSessionLocal() as session:
            deployment = await session.get(Deployment, deployment_id)
            if deployment is None:
                raise HTTPException(status_code=404, detail="Deployment not found")
            if body.name is not None:
                deployment.name = body.name
            if body.base_url is not None:
                deployment.base_url = body.base_url
            if body.profile is not None:
                deployment.profile = json.dumps(body.profile, ensure_ascii=False)
            if body.is_active is not None:
                deployment.is_active = "true" if body.is_active else "false"
            await session.commit()
            return _deployment_to_dict(deployment)

    @app.delete("/api/v1/deployments/{deployment_id}", dependencies=[Depends(require_admin)])
    async def delete_deployment(deployment_id: str) -> dict[str, str]:
        async with AsyncSessionLocal() as session:
            deployment = await session.get(Deployment, deployment_id)
            if deployment is None:
                raise HTTPException(status_code=404, detail="Deployment not found")
            await session.delete(deployment)
            await session.commit()
        return {"status": "deleted"}

    @app.get("/api/v1/deployments/{deployment_id}/usage-history", dependencies=[Depends(require_admin)])
    async def usage_history(deployment_id: str, limit: int = 500) -> dict[str, Any]:
        """Usage snapshots over time (newest first) for trend/billing views."""
        import json

        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(UsageRecord)
                .where(UsageRecord.deployment_id == deployment_id)
                .order_by(UsageRecord.created_at.desc())
                .limit(min(limit, 5000))
            )
            records = rows.scalars().all()
        return {
            "records": [
                {"at": r.created_at.isoformat() if r.created_at else None,
                 "usage": json.loads(r.usage)}
                for r in records
            ]
        }

    # -------------------------------------------- heartbeat (from products)

    @app.post("/api/v1/heartbeat")
    async def heartbeat(body: HeartbeatRequest) -> dict[str, Any]:
        import json

        async with AsyncSessionLocal() as session:
            deployment = await session.get(Deployment, body.deployment_id)
            if deployment is None or not secrets.compare_digest(
                deployment.license_key, body.license_key
            ):
                raise HTTPException(status_code=401, detail="Unknown deployment or bad license key.")
            if deployment.is_active != "true":
                raise HTTPException(status_code=403, detail="License is deactivated.")
            deployment.last_heartbeat = datetime.utcnow()
            if body.version:
                deployment.version = body.version
            if body.capabilities:
                deployment.capabilities = json.dumps(body.capabilities)
            if body.usage is not None:
                deployment.usage = json.dumps(body.usage)
                # append to the usage time-series (billing / trend data)
                session.add(
                    UsageRecord(deployment_id=deployment.id, usage=json.dumps(body.usage))
                )
            await session.commit()
            profile = json.loads(deployment.profile) if deployment.profile else {}
        # Returning the profile lets a deployment pick up config changes on the
        # next heartbeat without a redeploy.
        return {"status": "ok", "profile": profile}

    return app


app = create_app()

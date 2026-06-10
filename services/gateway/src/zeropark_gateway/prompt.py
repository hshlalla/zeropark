from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from zeropark_core.database import AsyncSessionLocal
from zeropark_core.models_db import PromptTemplate, PromptVersion
from zeropark_gateway.auth import get_current_user
from pydantic import BaseModel
from typing import Any

prompt_router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])

class PromptCreateRequest(BaseModel):
    workspace_id: str
    name: str
    description: str | None = None
    content: str

class PromptVersionCreateRequest(BaseModel):
    version_tag: str
    content: str

@prompt_router.post("")
async def create_prompt(body: PromptCreateRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        template = PromptTemplate(
            workspace_id=body.workspace_id,
            name=body.name,
            description=body.description
        )
        session.add(template)
        await session.flush()
        
        version = PromptVersion(
            template_id=template.id,
            version_tag="v1",
            content=body.content,
            is_active=True
        )
        session.add(version)
        await session.commit()
        return {"id": template.id, "name": template.name, "version": version.version_tag}

@prompt_router.post("/{template_id}/versions")
async def add_prompt_version(template_id: str, body: PromptVersionCreateRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        template = await session.get(PromptTemplate, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        version = PromptVersion(
            template_id=template.id,
            version_tag=body.version_tag,
            content=body.content,
            is_active=False
        )
        session.add(version)
        await session.commit()
        return {"id": version.id, "version_tag": version.version_tag}

@prompt_router.post("/{template_id}/versions/{version_id}/activate")
async def activate_version(template_id: str, version_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Rollback or switch active version."""
    async with AsyncSessionLocal() as session:
        # deactivate all
        versions = await session.execute(select(PromptVersion).where(PromptVersion.template_id == template_id))
        target_version = None
        for v in versions.scalars():
            if v.id == version_id:
                v.is_active = True
                target_version = v
            else:
                v.is_active = False
        
        if not target_version:
            raise HTTPException(status_code=404, detail="Version not found")
            
        await session.commit()
        return {"status": "success", "active_version": target_version.version_tag}

@prompt_router.get("/{template_id}")
async def get_prompt(template_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        template = await session.get(PromptTemplate, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        versions = await session.execute(
            select(PromptVersion)
            .where(PromptVersion.template_id == template_id)
            .order_by(PromptVersion.created_at.desc())
        )
        
        return {
            "id": template.id,
            "name": template.name,
            "versions": [
                {
                    "id": v.id,
                    "version_tag": v.version_tag,
                    "content": v.content,
                    "is_active": v.is_active,
                    "created_at": v.created_at.isoformat()
                }
                for v in versions.scalars()
            ]
        }

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy import select
from zeropark_core.database import AsyncSessionLocal
from zeropark_core.models_db import Dataset, Document, DocumentChunk
from zeropark_gateway.auth import get_current_user
from pydantic import BaseModel
from typing import Any
import asyncio

dataset_router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])

class DatasetCreateRequest(BaseModel):
    workspace_id: str
    name: str
    description: str | None = None

@dataset_router.post("")
async def create_dataset(body: DatasetCreateRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        dataset = Dataset(
            workspace_id=body.workspace_id,
            name=body.name,
            description=body.description
        )
        session.add(dataset)
        await session.commit()
        return {"id": dataset.id, "name": dataset.name}

@dataset_router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        dataset = await session.get(Dataset, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        docs = await session.execute(select(Document).where(Document.dataset_id == dataset_id))
        
        return {
            "id": dataset.id,
            "name": dataset.name,
            "documents": [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "status": d.status,
                    "word_count": d.word_count
                }
                for d in docs.scalars()
            ]
        }

async def _process_document_chunking(document_id: str, content: str):
    """Background task to simulate chunking and embedding."""
    await asyncio.sleep(2) # simulate processing
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, document_id)
        if not doc:
            return
            
        # simple chunking simulation
        chunks = [content[i:i+500] for i in range(0, len(content), 500)]
        for idx, text in enumerate(chunks):
            chunk = DocumentChunk(
                document_id=doc.id,
                content=text,
                vector_id=f"vec_{doc.id}_{idx}"
            )
            session.add(chunk)
            
        doc.status = "completed"
        doc.word_count = str(len(content.split()))
        await session.commit()

@dataset_router.post("/{dataset_id}/documents")
async def upload_document(
    dataset_id: str, 
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    
    async with AsyncSessionLocal() as session:
        dataset = await session.get(Dataset, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        doc = Document(
            dataset_id=dataset.id,
            filename=file.filename,
            status="processing"
        )
        session.add(doc)
        await session.commit()
        
        background_tasks.add_task(_process_document_chunking, doc.id, text)
        return {"document_id": doc.id, "status": "processing"}

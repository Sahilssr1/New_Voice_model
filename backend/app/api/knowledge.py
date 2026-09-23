"""Knowledge-base endpoints: upload / list / delete documents, test search."""
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agents import _get_owned_agent
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services import knowledge_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["knowledge"])


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str = ""
    char_count: int = 0
    chunk_count: int = 0
    created_at: str = ""

    model_config = {"from_attributes": True}


class SearchIn(BaseModel):
    query: str
    top_k: int = 3


class SearchHit(BaseModel):
    filename: str
    text: str
    score: float


def _doc_out(doc) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type or "",
        char_count=doc.char_count or 0,
        chunk_count=doc.chunk_count or 0,
        created_at=str(doc.created_at) if doc.created_at else "",
    )


@router.post("/agents/{agent_id}/kb/documents", response_model=DocumentOut)
async def upload_document(
    agent_id: str,
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(agent_id, current, db)
    content = await file.read()
    try:
        doc = await knowledge_service.add_document(
            db,
            agent.id,
            file.filename or "upload",
            content,
            file.content_type or "",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _doc_out(doc)


@router.get("/agents/{agent_id}/kb/documents", response_model=list[DocumentOut])
async def list_documents(
    agent_id: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(agent_id, current, db)
    docs = await knowledge_service.list_documents(db, agent.id)
    return [_doc_out(d) for d in docs]


@router.delete("/agents/{agent_id}/kb/documents/{doc_id}")
async def delete_document(
    agent_id: str,
    doc_id: str,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(agent_id, current, db)
    ok = await knowledge_service.delete_document(db, agent.id, doc_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return {"deleted": True}


@router.post("/agents/{agent_id}/kb/search", response_model=list[SearchHit])
async def search_knowledge(
    agent_id: str,
    body: SearchIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test retrieval: what would the agent see for this query?"""
    agent = await _get_owned_agent(agent_id, current, db)
    hits = await knowledge_service.search(
        db, agent.id, body.query, top_k=max(1, min(body.top_k, 10))
    )
    return [
        SearchHit(filename=h["filename"], text=h["text"], score=round(h["score"], 3))
        for h in hits
    ]

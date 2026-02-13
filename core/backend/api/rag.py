"""
RAG API Endpoints
Provides RESTful API for RAG operations on Project knowledge bases
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from domains.knowledge.rag_service import RAGService
from domains.identity.auth import resolve_identity, Identity
from shared.database import get_async_db, Project
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from shared.paths import get_project_dir

router = APIRouter(prefix="/api/rag", tags=["RAG"])


# Pydantic models
class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    filter_file: Optional[str] = None


class SearchResult(BaseModel):
    content: str
    citation: str
    filename: str
    page: Optional[int]
    relevance_score:Optional[float]


class IndexRequest(BaseModel):
    reindex: bool = False


class IndexResponse(BaseModel):
    status: str
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    details: List[dict] = []


async def _verify_project(db: AsyncSession, user_id: str, project_id: str):
    """Common project existence check using Project table."""
    stmt = select(Project.id).filter(Project.user_id == user_id, Project.id == project_id)
    if not (await db.execute(stmt)).scalars().first():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")


@router.post("/{project_id}/search", response_model=List[SearchResult])
async def search_knowledge_base(
    project_id: str,
    req: SearchRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Semantic search in a Project's knowledge base
    """
    try:
        await _verify_project(db, identity.user_id, project_id)

        rag = RAGService(identity.user_id, project_id, db)
        results = await rag.search(req.query, req.n_results, req.filter_file)
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/{project_id}/index", response_model=IndexResponse)
async def index_refs_directory(
    project_id: str,
    req: IndexRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Index all PDFs in the Project's refs/ directory
    """
    try:
        await _verify_project(db, identity.user_id, project_id)

        rag = RAGService(identity.user_id, project_id, db)
        results = await rag.index_directory()
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.post("/{project_id}/upload")
async def upload_reference_file(
    project_id: str,
    file: UploadFile = File(...),
    auto_index: bool = True,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Upload a PDF file to the Project's refs/ directory
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        import aiofiles

        await _verify_project(db, identity.user_id, project_id)

        # Save file
        refs_dir = get_project_dir(identity.user_id, project_id) / "refs"
        refs_dir.mkdir(parents=True, exist_ok=True)

        file_path = refs_dir / file.filename

        async with aiofiles.open(file_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        response = {
            "filename": file.filename,
            "file_path": str(file_path),
            "uploaded": True
        }

        # Auto-index if requested
        if auto_index:
            rag = RAGService(identity.user_id, project_id, db)
            index_result = await rag.index_pdf(file_path)
            response["index_result"] = index_result

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/{project_id}/files")
async def list_indexed_files(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List all indexed files in a Project's knowledge base
    """
    try:
        await _verify_project(db, identity.user_id, project_id)

        rag = RAGService(identity.user_id, project_id, db)
        files = await rag.get_indexed_files()
        return {"files": files}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/{project_id}/stats")
async def get_rag_stats(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get RAG statistics for a Project
    """
    try:
        await _verify_project(db, identity.user_id, project_id)

        rag = RAGService(identity.user_id, project_id, db)
        stats = await rag.get_stats()
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/{project_id}/rebuild")
async def rebuild_index(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Rebuild the entire RAG index from scratch
    """
    try:
        await _verify_project(db, identity.user_id, project_id)

        rag = RAGService(identity.user_id, project_id, db)
        results = await rag.rebuild_index()
        return {
            "rebuilt": True,
            **results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {str(e)}")


@router.delete("/{project_id}/files/{filename}")
async def delete_reference_file(
    project_id: str,
    filename: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete a reference file and remove from index
    """
    await _verify_project(db, identity.user_id, project_id)

    file_path = get_project_dir(identity.user_id, project_id) / "refs" / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
        return {
            "deleted": True,
            "filename": filename,
            "note": "File deleted. Run /rebuild to update index."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

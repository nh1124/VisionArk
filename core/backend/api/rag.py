"""
RAG API Endpoints
Provides RESTful API for RAG operations on Spoke knowledge bases
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import shutil

from services.rag_service import RAGService
from services.auth import resolve_identity, Identity, get_db
from utils.paths import get_spoke_dir

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


@router.post("/{spoke_name}/search", response_model=List[SearchResult])
async def search_knowledge_base(
    spoke_name: str,
    req: SearchRequest,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Semantic search in a Spoke's knowledge base
    """
    try:
        rag = RAGService(identity.user_id, spoke_name, db)
        results = rag.search(req.query, req.n_results, req.filter_file)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/{spoke_name}/index", response_model=IndexResponse)
async def index_refs_directory(
    spoke_name: str,
    req: IndexRequest,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Index all PDFs in the Spoke's refs/ directory
    """
    try:
        rag = RAGService(identity.user_id, spoke_name, db)
        results = rag.index_directory()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.post("/{spoke_name}/upload")
async def upload_reference_file(
    spoke_name: str,
    file: UploadFile = File(...),
    auto_index: bool = True,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Upload a PDF file to the Spoke's refs/ directory
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        # Save file
        refs_dir = get_spoke_dir(identity.user_id, spoke_name) / "refs"
        refs_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = refs_dir / file.filename
        
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        response = {
            "filename": file.filename,
            "file_path": str(file_path),
            "uploaded": True
        }
        
        # Auto-index if requested
        if auto_index:
            rag = RAGService(identity.user_id, spoke_name, db)
            index_result = rag.index_pdf(file_path)
            response["index_result"] = index_result
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/{spoke_name}/files")
async def list_indexed_files(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    List all indexed files in a Spoke's knowledge base
    """
    try:
        rag = RAGService(identity.user_id, spoke_name, db)
        files = rag.get_indexed_files()
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/{spoke_name}/stats")
async def get_rag_stats(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Get RAG statistics for a Spoke
    """
    try:
        rag = RAGService(identity.user_id, spoke_name, db)
        stats = rag.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/{spoke_name}/rebuild")
async def rebuild_index(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Rebuild the entire RAG index from scratch
    """
    try:
        rag = RAGService(identity.user_id, spoke_name, db)
        results = rag.rebuild_index()
        return {
            "rebuilt": True,
            **results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {str(e)}")


@router.delete("/{spoke_name}/files/{filename}")
async def delete_reference_file(
    spoke_name: str,
    filename: str,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Delete a reference file and remove from index
    """
    file_path = get_spoke_dir(identity.user_id, spoke_name) / "refs" / filename
    
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

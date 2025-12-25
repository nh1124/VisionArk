"""
RAG Service
Combines PDF processing and vector store for complete RAG workflow
"""
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from .pdf_processor import PDFProcessor
from .vector_store import get_vector_store
from utils.paths import get_spoke_dir


class RAGService:
    """High-level RAG operations for a Spoke (per-user)"""
    
    def __init__(self, user_id: str, spoke_name: str, session: Optional[Session] = None):
        self.user_id = user_id
        self.spoke_name = spoke_name
        self.session = session
        self.vector_store = get_vector_store(user_id, spoke_name)
        self.pdf_processor = PDFProcessor(chunk_size=800, chunk_overlap=150)
        self.refs_dir = get_spoke_dir(user_id, spoke_name) / "refs"
        self.refs_dir.mkdir(parents=True, exist_ok=True)
    
    def index_pdf(self, pdf_path: Path, reindex: bool = False) -> Dict:
        """
        Index a PDF file into the vector store
        """
        # Check if already indexed
        file_info = self.pdf_processor.get_file_info(pdf_path)
        file_hash = file_info["file_hash"]
        
        if not reindex and self._is_indexed(pdf_path, file_hash):
            return {
                "status": "skipped",
                "reason": "already_indexed",
                "file": str(pdf_path)
            }
        
        # Process PDF into chunks
        chunks_data = self.pdf_processor.process_pdf(pdf_path, chunk=True)
        
        # Add to vector store
        contents = [chunk["content"] for chunk in chunks_data]
        metadatas = [chunk["metadata"] for chunk in chunks_data]
        
        # Generate IDs from content + metadata
        ids = [f"{file_hash}_{i}" for i in range(len(chunks_data))]
        
        self.vector_store.add_documents_batch(contents, metadatas, ids)
        
        # Update database tracking
        if self.session:
            self._update_index_metadata(pdf_path, file_hash, len(chunks_data))
        
        return {
            "status": "indexed",
            "file": str(pdf_path),
            "chunks_created": len(chunks_data),
            "pages": file_info["page_count"]
        }
    
    def index_directory(self, directory: Optional[Path] = None) -> Dict:
        """
        Index all PDFs in a directory (defaults to refs/ folder)
        """
        if directory is None:
            directory = self.refs_dir
        
        pdf_files = list(directory.glob("**/*.pdf"))
        
        results = {
            "total_files": len(pdf_files),
            "indexed": 0,
            "skipped": 0,
            "failed": 0,
            "details": []
        }
        
        for pdf_path in pdf_files:
            try:
                result = self.index_pdf(pdf_path)
                results["details"].append(result)
                
                if result["status"] == "indexed":
                    results["indexed"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "status": "error",
                    "file": str(pdf_path),
                    "error": str(e)
                })
        
        return results
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_file: Optional[str] = None
    ) -> List[Dict]:
        """
        Search for relevant content
        """
        # Build metadata filter
        filter_metadata = None
        if filter_file:
            filter_metadata = {"filename": filter_file}
        
        # Search vector store
        results = self.vector_store.search(query, n_results, filter_metadata)
        
        # Format with citations
        formatted_results = []
        for result in results:
            metadata = result["metadata"]
            formatted_results.append({
                "content": result["content"],
                "citation": self._format_citation(metadata),
                "filename": metadata.get("filename", "Unknown"),
                "page": metadata.get("page", None),
                "relevance_score": 1.0 - (result["distance"] or 0) if result["distance"] is not None else None
            })
        
        return formatted_results
    
    def get_indexed_files(self) -> List[Dict]:
        """Get list of indexed files with metadata"""
        if not self.session:
            return []
        
        query = text("""
            SELECT file_name, file_path, file_hash, indexed_at, chunk_count
            FROM rag_metadata
            WHERE spoke_name = :spoke_name AND user_id = :user_id
            ORDER BY indexed_at DESC
        """)
        
        result = self.session.execute(query, {
            "spoke_name": self.spoke_name,
            "user_id": self.user_id
        })
        
        return [
            {
                "filename": row[0],
                "file_path": row[1],
                "file_hash": row[2],
                "indexed_at": row[3],
                "chunk_count": row[4]
            }
            for row in result
        ]
    
    def remove_file(self, filename: str):
        """Remove a file from the index"""
        pass
    
    def rebuild_index(self):
        """Rebuild the entire index from scratch"""
        self.vector_store.clear()
        return self.index_directory()
    
    def get_stats(self) -> Dict:
        """Get RAG statistics for this Spoke"""
        vector_stats = self.vector_store.get_stats()
        
        stats = {
            "user_id": self.user_id,
            "spoke_name": self.spoke_name,
            "vector_store": vector_stats,
            "refs_directory": str(self.refs_dir),
            "pdf_count": len(list(self.refs_dir.glob("**/*.pdf")))
        }
        
        if self.session:
            indexed_files = self.get_indexed_files()
            stats["indexed_files"] = len(indexed_files)
            stats["total_chunks"] = sum(f["chunk_count"] for f in indexed_files)
        
        return stats
    
    def _is_indexed(self, pdf_path: Path, file_hash: str) -> bool:
        """Check if a file is already indexed with the same hash"""
        if not self.session:
            return False
        
        query = text("""
            SELECT file_hash FROM rag_metadata
            WHERE spoke_name = :spoke_name AND user_id = :user_id AND file_path = :file_path
        """)
        
        result = self.session.execute(query, {
            "spoke_name": self.spoke_name,
            "user_id": self.user_id,
            "file_path": str(pdf_path)
        }).fetchone()
        
        return result and result[0] == file_hash
    
    def _update_index_metadata(self, pdf_path: Path, file_hash: str, chunk_count: int):
        """Update database tracking for indexed files"""
        upsert_query = text("""
            INSERT INTO rag_metadata (spoke_name, user_id, file_name, file_path, file_hash, chunk_count, indexed_at)
            VALUES (:spoke_name, :user_id, :file_name, :file_path, :file_hash, :chunk_count, :indexed_at)
            ON CONFLICT(spoke_name, user_id, file_path) DO UPDATE SET
                file_hash = :file_hash,
                chunk_count = :chunk_count,
                indexed_at = :indexed_at
        """)
        
        self.session.execute(upsert_query, {
            "spoke_name": self.spoke_name,
            "user_id": self.user_id,
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "file_hash": file_hash,
            "chunk_count": chunk_count,
            "indexed_at": datetime.utcnow()
        })
        self.session.commit()
    
    def _format_citation(self, metadata: Dict) -> str:
        """Format a citation string"""
        filename = metadata.get("filename", "Unknown")
        page = metadata.get("page")
        
        if page:
            return f"{filename}, p.{page}"
        return filename

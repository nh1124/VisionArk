"""
Vector Store Service
Manages ChromaDB vector stores for RAG in each Spoke
"""
import os
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from infrastructure.llm import GeminiLLMProvider
from shared.paths import get_project_dir, get_user_projects_dir


class VectorStore:
    """Vector store for a single Project's knowledge base (per-user)"""
    
    def __init__(self, user_id: str, project_id: str):
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB not installed. Run: pip install chromadb>=0.4.22")
        
        self.user_id = user_id
        self.project_id = project_id
        self.store_path = get_project_dir(user_id, project_id) / "vector_store"
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.store_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=f"{project_id}_refs",
            metadata={"description": f"Reference documents for {project_id}"}
        )
        
        # LLM provider for embeddings (lazy loaded)
        self._llm = None
        self._api_key = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = GeminiLLMProvider(api_key=self._api_key)
        return self._llm

    def set_api_key(self, api_key: str):
        """Update API key and reset provider"""
        if api_key and api_key != self._api_key:
            self._api_key = api_key
            self._llm = None
    
    def add_document(
        self,
        content: str,
        metadata: Dict,
        doc_id: Optional[str] = None
    ) -> str:
        """
        Add a document to the vector store
        
        Args:
            content: Text content to embed
            metadata: Document metadata (filename, page, etc.)
            doc_id: Optional custom ID (auto-generated if not provided)
        
        Returns:
            Document ID
        """
        if doc_id is None:
            # Generate ID from content hash
            doc_id = hashlib.md5(content.encode()).hexdigest()
        
        # Generate embedding
        try:
            embedding = self.llm.embed(content)
        except Exception as e:
            print(f"Warning: Failed to generate embedding: {e}")
            # Fallback: use simple hash-based ID
            embedding = None
        
        # Add to collection
        if embedding:
            self.collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id]
            )
        else:
            # Store without embedding (searchable by metadata only)
            self.collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id]
            )
        
        return doc_id
    
    def add_documents_batch(
        self,
        contents: List[str],
        metadatas: List[Dict],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        Add multiple documents in batch (more efficient)
        
        Args:
            contents: List of text contents
            metadatas: List of metadata dicts
            ids: Optional list of IDs
        
        Returns:
            List of document IDs
        """
        if ids is None:
            ids = [hashlib.md5(c.encode()).hexdigest() for c in contents]
        
        # Generate embeddings in batch
        try:
            embeddings = [self.llm.embed(content) for content in contents]
            
            self.collection.add(
                embeddings=embeddings,
                documents=contents,
                metadatas=metadatas,
                ids=ids
            )
        except Exception as e:
            print(f"Warning: Batch embedding failed: {e}")
            # Fallback to no embeddings
            self.collection.add(
                documents=contents,
                metadatas=metadatas,
                ids=ids
            )
        
        return ids
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Semantic search for relevant documents
        
        Args:
            query: Search query text
            n_results: Number of results to return
            filter_metadata: Optional metadata filters
        
        Returns:
            List of result dicts with content, metadata, distance
        """
        # Generate query embedding
        try:
            query_embedding = self.llm.embed(query)
        except Exception as e:
            print(f"Search failed: {e}")
            return []
        
        # Search collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_metadata
        )
        
        # Format results
        formatted_results = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    "content": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results['distances'] else None,
                    "id": results['ids'][0][i] if results['ids'] else None
                })
        
        return formatted_results
    
    def get_by_id(self, doc_id: str) -> Optional[Dict]:
        """Get a specific document by ID"""
        result = self.collection.get(ids=[doc_id])
        
        if result and result['documents']:
            return {
                "content": result['documents'][0],
                "metadata": result['metadatas'][0] if result['metadatas'] else {},
                "id": doc_id
            }
        return None
    
    def delete_document(self, doc_id: str):
        """Delete a document from the store"""
        self.collection.delete(ids=[doc_id])
    
    def get_stats(self) -> Dict:
        """Get statistics about the vector store"""
        count = self.collection.count()
        
        return {
            "project_id": self.project_id,
            "document_count": count,
            "store_path": str(self.store_path),
            "collection_name": self.collection.name
        }
    
    def clear(self):
        """Clear all documents from the store"""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.create_collection(
            name=f"{self.project_id}_refs"
        )


class VectorStoreManager:
    """Manages vector stores for all Projects across all users"""
    
    def __init__(self):
        self._stores: Dict[str, VectorStore] = {}
    
    def get_store(self, user_id: str, project_id: str) -> VectorStore:
        """Get or create a vector store for a Project"""
        cache_key = f"{user_id}:{project_id}"
        if cache_key not in self._stores:
            self._stores[cache_key] = VectorStore(user_id, project_id)
        return self._stores[cache_key]
    
    def list_stores(self, user_id: str) -> List[str]:
        """List all existing Project vector stores for a user"""
        user_projects_dir = get_user_projects_dir(user_id)
        if not user_projects_dir.exists():
            return []
        
        stores = []
        for project_dir in user_projects_dir.iterdir():
            if project_dir.is_dir() and (project_dir / "vector_store").exists():
                stores.append(project_dir.name)
        
        return stores


# Global manager instance
_manager = VectorStoreManager()


def get_vector_store(user_id: str, project_id: str) -> VectorStore:
    """Get vector store for a Project (singleton pattern, per-user)"""
    return _manager.get_store(user_id, project_id)

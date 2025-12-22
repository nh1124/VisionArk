"""
PDF Processing Service
Extracts text from PDFs and chunks for RAG indexing
"""
from pathlib import Path
from typing import List, Dict, Tuple
import hashlib

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


class PDFProcessor:
    """Process PDF files for RAG indexing"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize PDF processor
        
        Args:
            chunk_size: Target size of text chunks in characters
            chunk_overlap: Overlap between chunks for context preservation
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        if not PYPDF_AVAILABLE:
            raise ImportError("pypdf not installed. Run: pip install pypdf>=3.17.0")
    
    def extract_text(self, pdf_path: Path, method: str = "pypdf") -> str:
        """
        Extract all text from a PDF
        
        Args:
            pdf_path: Path to PDF file
            method: Extraction method ('pypdf' or 'pdfplumber')
        
        Returns:
            Extracted text
        """
        if method == "pdfplumber" and PDFPLUMBER_AVAILABLE:
            return self._extract_with_pdfplumber(pdf_path)
        else:
            return self._extract_with_pypdf(pdf_path)
    
    def _extract_with_pypdf(self, pdf_path: Path) -> str:
        """Extract text using pypdf (simple, fast)"""
        reader = PdfReader(pdf_path)
        text_parts = []
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    def _extract_with_pdfplumber(self, pdf_path: Path) -> str:
        """Extract text using pdfplumber (better layout preservation)"""
        text_parts = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    def extract_with_metadata(self, pdf_path: Path) -> List[Dict]:
        """
        Extract text with page-level metadata
        
        Returns:
            List of dicts with 'text' and 'metadata' (page number, etc.)
        """
        reader = PdfReader(pdf_path)
        pages_data = []
        
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                pages_data.append({
                    "text": text,
                    "metadata": {
                        "filename": pdf_path.name,
                        "page": page_num,
                        "total_pages": len(reader.pages),
                        "file_path": str(pdf_path)
                    }
                })
        
        return pages_data
    
    def chunk_text(self, text: str, preserve_sentences: bool = True) -> List[str]:
        """
        Split text into chunks for indexing
        
        Args:
            text: Text to chunk
            preserve_sentences: Try to keep sentences intact
        
        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            
            # If not at the end, try to break at sentence boundary
            if end < len(text) and preserve_sentences:
                # Look for sentence endings near the chunk boundary
                search_start = max(start, end - 100)
                search_end = min(len(text), end + 100)
                
                # Find last sentence ending in range
                for punct in ['. ', '.\n', '! ', '?\n', '? ']:
                    last_punct = text.rfind(punct, search_start, search_end)
                    if last_punct != -1:
                        end = last_punct + len(punct)
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start with overlap
            start = end - self.chunk_overlap
        
        return chunks
    
    def process_pdf(
        self,
        pdf_path: Path,
        chunk: bool = True
    ) -> List[Dict]:
        """
        Complete PDF processing pipeline
        
        Args:
            pdf_path: Path to PDF file
            chunk: Whether to chunk the text
        
        Returns:
            List of chunks with metadata
        """
        # Extract with page metadata
        pages_data = self.extract_with_metadata(pdf_path)
        
        # Generate file hash for deduplication
        file_hash = self._compute_file_hash(pdf_path)
        
        chunks_data = []
        
        for page_data in pages_data:
            page_text = page_data["text"]
            page_metadata = page_data["metadata"]
            page_metadata["file_hash"] = file_hash
            
            if chunk:
                # Split page into chunks
                page_chunks = self.chunk_text(page_text)
                
                for chunk_idx, chunk_text in enumerate(page_chunks):
                    chunk_metadata = page_metadata.copy()
                    chunk_metadata["chunk_index"] = chunk_idx
                    chunk_metadata["total_chunks_on_page"] = len(page_chunks)
                    
                    chunks_data.append({
                        "content": chunk_text,
                        "metadata": chunk_metadata
                    })
            else:
                # Use entire page as one chunk
                chunks_data.append({
                    "content": page_text,
                    "metadata": page_metadata
                })
        
        return chunks_data
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute MD5 hash of file for change detection"""
        md5_hash = hashlib.md5()
        
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        
        return md5_hash.hexdigest()
    
    def get_file_info(self, pdf_path: Path) -> Dict:
        """Get basic information about a PDF"""
        reader = PdfReader(pdf_path)
        
        return {
            "filename": pdf_path.name,
            "file_path": str(pdf_path),
            "file_hash": self._compute_file_hash(pdf_path),
            "page_count": len(reader.pages),
            "file_size_bytes": pdf_path.stat().st_size,
            "metadata": reader.metadata if hasattr(reader, 'metadata') else {}
        }

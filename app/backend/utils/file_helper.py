"""
Helper function to process uploaded files
Extracts text from PDFs, images, etc.
"""
import PyPDF2
import io


async def process_file_content(file_content: bytes, filename: str, content_type: str) -> str:
    """
    Process file and extract readable content
    
    Returns:
        Formatted string with file content for LLM
    """
    try:
        # PDF files
        if content_type == "application/pdf":
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            text_parts = []
            for page_num, page in enumerate(pdf_reader.pages):
                text_parts.append(f"--- Page {page_num + 1} ---\n{page.extract_text()}")
            pdf_text = "\n\n".join(text_parts)
            return f"## File: {filename}\n{pdf_text}"
        
        # Text files
        elif content_type.startswith("text/") or filename.endswith((".txt", ".md", ".json", ".csv")):
            text = file_content.decode('utf-8')
            return f"## File: {filename}\n{text}"
        
        # Images (metadata only for now, full vision support coming)
        elif content_type.startswith("image/"):
            return f"## File: {filename}\n[Image file - {content_type}, {len(file_content)} bytes]\nNote: Image analysis coming in Phase 2"
        
        # Other files
        else:
            return f"## File: {filename}\n[File type {content_type} - {len(file_content)} bytes]\nNote: This file type is not yet supported for content extraction"
            
    except Exception as e:
        return f"## File: {filename}\n[Error processing file: {str(e)}]"


# Export for use in agents.py
__all__ = ['process_file_content']

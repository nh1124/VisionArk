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
        
        # Media files (Images, Audio)
        elif content_type.startswith("image/"):
            return f"## File: {filename}\n[Image file - {content_type}, {len(file_content)} bytes]\nNote: Analyzed via Gemini Native Multimodal"
        
        elif content_type.startswith("audio/"):
            return f"## File: {filename}\n[Audio file - {content_type}, {len(file_content)} bytes]\nNote: Analyzed via Gemini Native Audio"
        
        # Other files
        else:
            return f"## File: {filename}\n[File type {content_type} - {len(file_content)} bytes]\nNote: Content extraction via text fallback"
            
    except Exception as e:
        return f"## File: {filename}\n[Error processing file: {str(e)}]"


# Export for use in agents.py
__all__ = ['process_file_content']

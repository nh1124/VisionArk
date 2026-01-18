"""
File processing utilities
Extract text from PDFs, process images, etc.
"""
import base64
from pathlib import Path
from typing import Dict, Any, List
import PyPDF2
import io


async def process_uploaded_file(file_content: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    """
    Process an uploaded file and extract useful information
    
    Returns:
        dict with file info and processed content
    """
    result = {
        "name": filename,
        "type": content_type,
        "size": len(file_content),
        "processed_content": None,
        "gemini_part": None  # For Gemini API
    }
    
    # Process PDF files
    if content_type == "application/pdf":
        try:
            text = extract_text_from_pdf(file_content)
            result["processed_content"] = text
            result["summary"] = f"PDF with {len(text)} characters"
        except Exception as e:
            result["error"] = f"Failed to process PDF: {str(e)}"
    
    # Process media files (images, audio)
    elif content_type.startswith("image/") or content_type.startswith("audio/"):
        try:
            # Encode for Gemini API (Legacy inline_data fallback)
            b64_data = base64.b64encode(file_content).decode('utf-8')
            result["gemini_part"] = {
                "inline_data": {
                    "mime_type": content_type,
                    "data": b64_data
                }
            }
            media_type = "Image" if content_type.startswith("image/") else "Audio"
            result["summary"] = f"{media_type} ({content_type})"
        except Exception as e:
            result["error"] = f"Failed to process {content_type}: {str(e)}"
    
    # Process text files
    elif content_type.startswith("text/") or filename.endswith((".txt", ".md", ".json", ".csv")):
        try:
            text = file_content.decode('utf-8')
            result["processed_content"] = text
            result["summary"] = f"Text file with {len(text)} characters"
        except Exception as e:
            result["error"] = f"Failed to process text: {str(e)}"
    
    else:
        result["summary"] = f"Unsupported file type: {content_type}"
    
    return result


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """Extract text from PDF bytes"""
    try:
        pdf_file = io.BytesIO(pdf_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text_parts = []
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text_parts.append(f"--- Page {page_num + 1} ---\n{page.extract_text()}")
        
        return "\n\n".join(text_parts)
    except Exception as e:
        raise Exception(f"PDF extraction failed: {str(e)}")



async def save_file_to_project(user_id: str, file_content: bytes, filename: str, project_name: str, file_type: str = "refs") -> Path:
    """
    Save uploaded file to project directory (user-scoped)
    
    Args:
        user_id: User ID for scoped path
        file_content: File bytes
        filename: Original filename
        project_name: Project name
        file_type: "refs" or "artifacts"
    
    Returns:
        Path to saved file
    """
    from utils.paths import get_project_dir
    
    project_dir = get_project_dir(user_id, project_name)
    target_dir = project_dir / file_type
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Save file
    file_path = target_dir / filename
    file_path.write_bytes(file_content)
    
    return file_path

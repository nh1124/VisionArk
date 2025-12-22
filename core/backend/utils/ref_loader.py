"""
Helper to load reference files from spoke directory
"""
from pathlib import Path
from typing import List
import PyPDF2
import io


def load_reference_files(user_id: str, spoke_name: str, max_files: int = 5) -> str:
    """
    Load reference files from spoke's refs/ directory
    
    Args:
        user_id: User's UUID
        spoke_name: Name of the spoke
        max_files: Maximum number of reference files to load
    
    Returns:
        Formatted string with reference file contents
    """
    from utils.paths import get_spoke_dir
    
    spoke_dir = get_spoke_dir(user_id, spoke_name)
    refs_dir = spoke_dir / "refs"
    
    if not refs_dir.exists():
        return ""
    
    ref_contents = []
    file_count = 0
    
    for ref_file in refs_dir.iterdir():
        if file_count >= max_files:
            break
            
        if ref_file.is_file():
            try:
                # PDF files
                if ref_file.suffix.lower() == '.pdf':
                    content = ref_file.read_bytes()
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                    text_parts = [f"--- Page {i+1} ---\n{p.extract_text()}" 
                                 for i, p in enumerate(pdf_reader.pages)]
                    pdf_text = "\n\n".join(text_parts)
                    ref_contents.append(f"## Reference: {ref_file.name}\n{pdf_text}")
                    file_count += 1
                
                # Text files
                elif ref_file.suffix.lower() in ['.txt', '.md', '.json', '.csv']:
                    text = ref_file.read_text(encoding='utf-8')
                    ref_contents.append(f"## Reference: {ref_file.name}\n{text}")
                    file_count += 1
                    
            except Exception as e:
                print(f"Error loading reference {ref_file.name}: {e}")
                continue
    
    if ref_contents:
        return "\n\n**Reference Documents from Library:**\n\n" + "\n\n".join(ref_contents)
    return ""


__all__ = ['load_reference_files']

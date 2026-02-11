import mimetypes

_MIME_FALLBACK = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".py": "text/x-python",
    ".json": "application/json",
    ".js": "application/javascript",
    ".ts": "application/typescript",
    ".tsx": "application/typescript",
    ".jsx": "application/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".txt": "text/plain",
    ".sh": "text/x-shellscript",
    ".yml": "text/yaml",
    ".yaml": "text/yaml"
}

def guess_mime_type(filename: str) -> str:
    """
    Robust MIME type guessing with a manual fallback for common developer files.
    Ensures Gemini-compatible types for text-based files.
    """
    if not filename:
        return "application/octet-stream"
    
    mime, _ = mimetypes.guess_type(filename)
    if mime and mime != "application/octet-stream":
        return mime
    
    # Manual fallback for specific extensions
    import os
    ext = os.path.splitext(filename)[1].lower()
    return _MIME_FALLBACK.get(ext, "application/octet-stream")

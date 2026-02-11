
from typing import Optional, Dict, Any

class KnowledgeCoreError(Exception):
    """Base exception for KnowledgeCore SDK."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}

class AuthenticationError(KnowledgeCoreError):
    """Raised when authentication fails."""
    pass

class ValidationError(KnowledgeCoreError):
    """Raised when request validation fails."""
    pass

class ResourceNotFoundError(KnowledgeCoreError):
    """Raised when a resource is not found."""
    pass

class RateLimitError(KnowledgeCoreError):
    """Raised when rate limit is exceeded."""
    pass

class InternalServerError(KnowledgeCoreError):
    """Raised when the server encounters an internal error."""
    pass

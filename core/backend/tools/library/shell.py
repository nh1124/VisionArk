import logging
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from models.database import get_engine, get_session
from services.approval import ApprovalService

logger = logging.getLogger(__name__)

class RunSafeShellArgs(BaseModel):
    command: str = Field(..., description="The shell command to execute")
    cwd: Optional[str] = Field(None, description="The working directory relative to project root")
    timeout: int = Field(30, description="Execution timeout in seconds")

class RunSafeShellTool(BaseTool):
    name = "run_safe_shell"
    description = (
        "Queue a system command for execution. "
        "Commands are NOT executed immediately but are queued for human approval. "
        "The system will return a Request ID and status. "
        "Supported keys: command, cwd, timeout."
    )
    args_schema = RunSafeShellArgs

    async def run(self, command: str, cwd: Optional[str] = None, timeout: int = 30, **kwargs) -> Any:
        # Context extraction (assuming injected by BaseNode)
        user_id = kwargs.get("user_id")
        project_id = kwargs.get("project_id")
        
        if not user_id or not project_id:
             # Fallback/Error if context is missing
             return {
                 "success": False, 
                 "error": "Missing execution context (user_id/project_id). Cannot queue approval."
             }

        engine = get_engine()
        db = get_session(engine)
        
        try:
            # Create Approval Request via Service
            payload = {
                "command": command,
                "cwd": cwd,
                "timeout": timeout
            }
            
            request = ApprovalService.create_request(
                db, 
                project_id, 
                user_id, 
                "run_safe_shell", 
                payload
            )
            
            return {
                "success": True,
                "status": "pending_approval",
                "request_id": request.id,
                "command": command,
                "message": (
                    "COMMAND QUEUED FOR APPROVAL:\n\n"
                    f"**Command:** `{command}`\n"
                    f"**Request ID:** `{request.id}`\n\n"
                    "Please approve this action in the UI to proceed with execution."
                )
            }
            
        except Exception as e:
            logger.error(f"Failed to queue shell command: {e}")
            return {
                "success": False,
                "error": f"Failed to queue command: {str(e)}"
            }
        finally:
            db.close()

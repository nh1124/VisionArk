from datetime import datetime
import json
import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from models.database import ApprovalRequest, ApprovalStatus
from utils.paths import secure_path_join, get_project_dir
import subprocess
import os

logger = logging.getLogger(__name__)

class ApprovalService:
    @staticmethod
    def create_request(
        db: Session, 
        project_id: str, 
        user_id: str, 
        tool_name: str, 
        payload: dict
    ) -> ApprovalRequest:
        """
        Create a new approval request in PENDING state.
        """
        request_id = str(uuid.uuid4())
        
        # Create DB record
        request = ApprovalRequest(
            id=request_id,
            project_id=project_id,
            user_id=user_id,
            tool_name=tool_name,
            payload=payload,
            status=ApprovalStatus.PENDING,
        )
        
        db.add(request)
        db.commit()
        db.refresh(request)
        
        return request

    @staticmethod
    def approve_request(db: Session, request_id: str) -> ApprovalRequest:
        """
        Execute the approved request.
        """
        request = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == request_id))
        
        if not request:
            raise ValueError(f"Request {request_id} not found")
            
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Request is not pending (current status: {request.status})")

        # Execute based on tool name
        if request.tool_name == "run_safe_shell":
            result = ApprovalService._execute_shell(request)
        else:
            result = {"success": False, "error": f"Unknown tool: {request.tool_name}"}
            request.status = ApprovalStatus.FAILED

        # Update DB
        request.response = result
        if result.get("success"):
            request.status = ApprovalStatus.EXECUTED
        else:
            request.status = ApprovalStatus.FAILED
            request.error_log = result.get("error")
            
        request.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(request)
        return request

    @staticmethod
    def reject_request(db: Session, request_id: str) -> ApprovalRequest:
        """
        Reject the request.
        """
        request = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == request_id))
        
        if not request:
            raise ValueError(f"Request {request_id} not found")
            
        request.status = ApprovalStatus.REJECTED
        request.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(request)
        return request

    @staticmethod
    def _execute_shell(request: ApprovalRequest) -> dict:
        """
        Internal secure shell execution logic (moved from tool).
        """
        try:
            command = request.payload.get("command")
            cwd = request.payload.get("cwd")
            timeout = request.payload.get("timeout", 30)
            
            # 1. Resolve Project Root
            # Note: We rebuild the path logic here as this is the trusted execution environment
            project_root = get_project_dir(request.user_id, request.project_id)
            if not project_root.exists():
                return {"success": False, "error": "Project directory not found"}

            # 2. Resolve Working Directory
            if cwd:
                try:
                    work_dir = secure_path_join(project_root, cwd)
                except ValueError as e:
                    return {"success": False, "error": f"Invalid CWD: {str(e)}"}
            else:
                work_dir = project_root

            # 3. Whitelist Check (Redundant but safe)
            ALLOWED_COMMANDS = {
                "dir", "echo", "type", "mkdir", "rmdir", "copy", "move", "del", "ren",
                "python", "pip", "git", "node", "npm", "yarn",
                "whoami", "hostname", "ver", "set"
            }
            # Add strict whitelist check again just in case
            cmd_root = command.split()[0].lower() if command else ""
            if cmd_root not in ALLOWED_COMMANDS:
                 return {"success": False, "error": f"Command '{cmd_root}' is not in the whitelist (Double-check failed)"}

            # 4. Execution
            env = os.environ.copy()
            # Sanitize env if needed
            
            process = subprocess.run(
                command,
                shell=True,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='cp932', # Windows specific
                errors='ignore',
                env=env
            )
            
            return {
                "success": process.returncode == 0,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "returncode": process.returncode
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

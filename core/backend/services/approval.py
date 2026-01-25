from datetime import datetime
import json
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from models.database import ApprovalRequest, ApprovalStatus
from utils.paths import secure_path_join, get_project_dir
import subprocess
import os
import asyncio

logger = logging.getLogger(__name__)

class ApprovalService:
    @staticmethod
    def create_request(
        db, # Can be Session or AsyncSession, but we should aim for consistency
        project_id: str, 
        user_id: str, 
        tool_name: str, 
        payload: dict
    ) -> ApprovalRequest:
        """
        Create a new approval request in PENDING state.
        Synchronous for now as it's often called from tools that might still be sync.
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
    async def set_approved(db: AsyncSession, request_id: str) -> ApprovalRequest:
        """
        Transition request to APPROVED status. Does NOT execute.
        """
        stmt = select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        result = await db.execute(stmt)
        request = result.scalars().first()
        
        if not request:
            raise ValueError(f"Request {request_id} not found")
            
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Request is not pending (current status: {request.status})")

        request.status = ApprovalStatus.APPROVED
        request.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(request)
        return request

    @staticmethod
    async def execute_approved_request(db: AsyncSession, request_id: str) -> ApprovalRequest:
        """
        Execute the already APPROVED request in the worker.
        """
        stmt = select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        result = await db.execute(stmt)
        request = result.scalars().first()
        
        print(f"{__name__} Debug : {request}")

        if not request:
            raise ValueError(f"Request {request_id} not found")
            
        if request.status != ApprovalStatus.APPROVED:
            raise ValueError(f"Request is not in APPROVED state (current status: {request.status})")

        # Execute based on tool name
        print(f"{__name__} Debug : {request.tool_name}")
        if request.tool_name == "run_safe_shell":
            exec_result = await ApprovalService._execute_shell_async(request)
        else:
            exec_result = {"success": False, "error": f"Unknown tool: {request.tool_name}"}

        print(f"{__name__} Debug : {exec_result}")
        
        # Update DB
        request.response = exec_result
        if exec_result.get("success"):
            request.status = ApprovalStatus.EXECUTED
        else:
            request.status = ApprovalStatus.FAILED
            request.error_log = exec_result.get("error")
            
        request.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(request)

        print(f"{__name__} Debug : Finished {request}")

        return request

    @staticmethod
    async def reject_request(db: AsyncSession, request_id: str) -> ApprovalRequest:
        """
        Reject the request.
        """
        stmt = select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        result = await db.execute(stmt)
        request = result.scalars().first()
        
        if not request:
            raise ValueError(f"Request {request_id} not found")
            
        request.status = ApprovalStatus.REJECTED
        request.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(request)
        return request

    @staticmethod
    async def _execute_shell_async(request: ApprovalRequest) -> dict:
        """
        Asynchronous shell execution using asyncio.create_subprocess_shell.
        """
        try:
            command = request.payload.get("command")
            cwd = request.payload.get("cwd")
            timeout = request.payload.get("timeout", 30)
            
            project_root = get_project_dir(request.user_id, request.project_id)
            if not project_root.exists():
                return {"success": False, "error": "Project directory not found"}

            if cwd:
                try:
                    work_dir = secure_path_join(project_root, cwd)
                except ValueError as e:
                    return {"success": False, "error": f"Invalid CWD: {str(e)}"}
            else:
                work_dir = project_root

            # Whitelist Check
            ALLOWED_COMMANDS = {
                "dir", "echo", "type", "mkdir", "rmdir", "copy", "move", "del", "ren",
                "python", "pip", "git", "node", "npm", "yarn",
                "whoami", "hostname", "ver", "set"
            }
            cmd_root = command.split()[0].lower() if command else ""
            if cmd_root not in ALLOWED_COMMANDS:
                 return {"success": False, "error": f"Command '{cmd_root}' is not in the whitelist"}

            env = os.environ.copy()
            
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            try:
                stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=timeout)
                
                # Windows encoding
                stdout = stdout_data.decode('cp932', errors='ignore')
                stderr = stderr_data.decode('cp932', errors='ignore')
                
                return {
                    "success": process.returncode == 0,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": process.returncode
                }
            except asyncio.TimeoutExpired:
                process.kill()
                await process.wait()
                return {"success": False, "error": "Command timed out"}

        except Exception as e:
            logger.error(f"Async shell execution failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _execute_shell(request: ApprovalRequest) -> dict:
        """
        Internal sync shell execution (legacy).
        """
        try:
            command = request.payload.get("command")
            cwd = request.payload.get("cwd")
            timeout = request.payload.get("timeout", 30)
            
            project_root = get_project_dir(request.user_id, request.project_id)
            if not project_root.exists():
                return {"success": False, "error": "Project directory not found"}

            if cwd:
                try:
                    work_dir = secure_path_join(project_root, cwd)
                except ValueError as e:
                    return {"success": False, "error": f"Invalid CWD: {str(e)}"}
            else:
                work_dir = project_root

            ALLOWED_COMMANDS = {
                "dir", "echo", "type", "mkdir", "rmdir", "copy", "move", "del", "ren",
                "python", "pip", "git", "node", "npm", "yarn",
                "whoami", "hostname", "ver", "set"
            }
            cmd_root = command.split()[0].lower() if command else ""
            if cmd_root not in ALLOWED_COMMANDS:
                 return {"success": False, "error": f"Command '{cmd_root}' is not in the whitelist"}

            env = os.environ.copy()
            
            process = subprocess.run(
                command,
                shell=True,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='cp932',
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

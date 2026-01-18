from typing import Any, Dict
from nodes.base_node import BaseNode
from nodes.members.ruler import RulerNode
from nodes.system.scheduler_node import SchedulerNode
from nodes.project.project_node import ProjectNode
from services.command_parser import parse_command, execute_command
from models.database import AsyncSessionLocal
import os
from models.message import AttachedFile
from services.file_service import FileService
from models.database import UserSettings
from sqlalchemy import select
from utils.encryption import decrypt_string

class RouterNode(BaseNode):
    """
    The Dispatcher.
    Routes messages to the appropriate Node (Scheduler, Project, etc.)
    Also handles pre-processing (File Uploads, Command Execution).
    """
    
    def __init__(self, context: Dict[str, Any]):
        super().__init__(context)
        self.attached_files = []

    async def pre_process(self):
        """
        Handle file uploads if present in context.
        """
        print(f"[RouterNode] Pre-processing task: {self.task_id}")
        # Re-use existing file upload logic
        files_data = self.context.get("files", [])
        if not files_data:
            return

        print(f"[RouterNode] Processing {len(files_data)} files...")
        
        async with AsyncSessionLocal() as db:
            # Get API Key
            result = await db.execute(select(UserSettings).filter(UserSettings.user_id == self.user_id))
            settings = result.scalars().first()
            api_key = None
            if settings and settings.gemini_api_key:
                api_key = settings.gemini_api_key
            else:
                print(f"[RouterNode] No API Key available for FileService.")
            
            file_service = None
            if api_key:
                try:
                    file_service = FileService(db, self.user_id, api_key)
                except Exception as e:
                    print(f"[RouterNode] Failed to init FileService: {e}")

            for f_meta in files_data:
                file_path = f_meta.get("path")
                filename = f_meta.get("filename")
                mime_type = f_meta.get("mime_type")
                
                if not file_path or not os.path.exists(file_path):
                    continue
                
                try:
                    with open(file_path, "rb") as f:
                        content = f.read()
                    
                    gemini_file_uri = None
                    gemini_file_name = None
                    storage_path = None
                    
                    if file_service:
                        db_file = await file_service.save_file(
                            content=content,
                            filename=filename,
                            mime_type=mime_type,
                            project_id="root"  # Router usually handles root/hub context imports
                        )
                        storage_path = db_file.storage_path
                        
                        gemini_file = await file_service.upload_to_gemini(db_file)
                        if gemini_file:
                            gemini_file_uri = gemini_file["gemini_file_uri"]
                            gemini_file_name = gemini_file["gemini_file_name"]

                    attached_file = AttachedFile(
                        filename=filename,
                        file_type=mime_type,
                        size_bytes=len(content),
                        content=None,
                        gemini_file_uri=gemini_file_uri,
                        gemini_file_name=gemini_file_name,
                        storage_path=storage_path
                    )
                    self.attached_files.append(attached_file)
                    
                    try:
                        os.remove(file_path)
                    except: pass
                    
                except Exception as e:
                    print(f"[RouterNode] Error processing file {filename}: {e}")
        
        # Pass attached files to context so target nodes can access them
        self.context['attached_files'] = self.attached_files


    async def route(self, message: str) -> BaseNode:
        """
        Determine the target node based on message content/intent.
        Returns an INSTANCE of the target node.
        """
        msg_lower = message.strip().lower()

        # 1. Command Check (Execution is handled here for simplicity, or we could have a CommandNode)
        # For now, we keep Command logic inside Router or delegate if it's a specific node command.
        if message.strip().startswith('/'):
            # Check for specific node commands
            if msg_lower.startswith("/schedule"):
                return SchedulerNode(self.context)
            
            # TODO: If it's a generic system command, handle it here or return a generic result wrapper?
            # Current architecture: Router executes commands directly in process() if simple.
            # But we want to return a Node.
            # Let's return self (RouterNode) if it's a command it can handle?
            # Or we execute it here and return a "ResultNode"?
            # Simplest for V3 migration: Return self, and self.process() handles generic commands.
            return self

        # 2. Intent Analysis
        # If explicitly asking for scheduling
        if "schedule" in msg_lower or "reschedule" in msg_lower:
             return SchedulerNode(self.context)

        # 3. Default -> ProjectNode
        return ProjectNode(self.context)


    async def process(self, message: str) -> Any:
        """
        Fallback process method for generic commands if route() returns self.
        """
        if message.strip().startswith('/'):
            cmd = parse_command(message.strip())
            if cmd:
                print(f"[RouterNode] Executing system command: {cmd.name}")
                # Dynamic context based on current request
                context_name = self.context.get("project_name", "hub")
                context_type = "project" if context_name != "hub" else "hub"

                async with AsyncSessionLocal() as db:
                    result = await execute_command(
                        cmd,
                        context=context_type, 
                        context_type=context_type,
                        context_name=context_name,
                        session=db,
                        user_id=self.user_id
                    )
                    return result.message
        
        return "RouterNode: No operation performed."

    async def post_process(self, result: Any):
        pass

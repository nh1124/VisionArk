from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import time
import traceback
from datetime import datetime
from llm import get_provider
from models.message import Message, MessageRole, AttachedFile

class BaseNode(ABC):
    def __init__(self, context: Dict[str, Any], status_callback: Optional[Any] = None):
        self.context = context
        self.user_id = context.get("user_id")
        self.task_id = context.get("task_id")
        self.status_callback = status_callback
        # LLM Provider (Stateless: configured per call or context)
        self.llm = None 
        
        # New Class-Based Tools
        from tools.base import BaseTool
        self.tools: List[BaseTool] = []
        
    async def load_system_prompt(self, role_name: Optional[str] = None) -> str:
        """
        Load the system prompt from database (Node) or backend assets.
        Global + Role Specific + Dynamic Tool Descriptions.
        """
        from utils.paths import get_prompts_dir
        from models.database import AsyncSessionLocal, Node
        from sqlalchemy import select
        
        prompts_dir = get_prompts_dir()
        
        # 1. Load Global
        global_path = prompts_dir / "system" / "global.md"
        global_text = ""
        try:
            if global_path.exists():
                global_text = global_path.read_text(encoding='utf-8')
            else:
                print(f"[BaseNode] Warning: Global prompt not found at {global_path}")
                global_text = "You are a helpful AI assistant."
        except Exception as e:
            print(f"[BaseNode] Error loading global prompt: {e}")
            
        # 2. Load Role Specifics (DB Profile first, then Fallback to static Markdown)
        role_text = ""
        if role_name:
            # Try DB first
            async with AsyncSessionLocal() as db:
                try:
                    # Find node_id from context/project_id if possible
                    p_id = self.context.get("project_id")
                    profile_result = await db.execute(
                        select(Node).filter(
                            Node.project_id == p_id,
                            Node.role_name == role_name,
                            Node.status == "active"
                        )
                    )
                    profile = profile_result.scalars().first()
                    
                    if profile and profile.system_prompt:
                        print(f"[BaseNode] Using DB profile for {role_name} in {p_id}")
                        role_text = profile.system_prompt
                except Exception as e:
                    print(f"[BaseNode] DB error fetching role prompt: {e}")

            # Fallback to Markdown
            if not role_text:
                role_path = prompts_dir / "roles" / f"{role_name}.md"
                try:
                    if role_path.exists():
                        role_text = role_path.read_text(encoding='utf-8')
                    else:
                        print(f"[BaseNode] Warning: Role prompt not found for {role_name}")
                except Exception as e:
                    print(f"[BaseNode] Error loading role prompt: {e}")
        
        # 3. Dynamic Tool Descriptions
        tool_text = ""
        if self.tools:
            tool_text = "\n## Available Tools\n"
            for tool in self.tools:
                decl = tool.declaration()
                name = decl.get("name")
                desc = decl.get("description")
                tool_text += f"- `{name}`: {desc}\n"
        
        # 4. Combine
        parts = [p for p in [global_text, role_text, tool_text] if p]
        return "\n\n".join(parts) if parts else "You are a helpful AI assistant."
    
    async def pre_process(self):
        """Hook for loading data, files, or LBS status."""
        pass

    @abstractmethod
    async def process(self, message: str) -> Any:
        """Main logic (LLM or Command). Must be overridden."""
        raise NotImplementedError

    async def post_process(self, result: Any):
        """Hook for side effects (Advocate, saving logs)."""
        pass

    async def _execute_tool(self, tool, **kwargs):
        """
        Execute a tool with callback injection and status reporting.
        """
        tool_name = tool.name
        
        # Inject callback
        if hasattr(tool, 'set_status_callback'):
            tool.set_status_callback(self.status_callback)
            
        # Report Start
        if self.status_callback:
            await self.status_callback(f"Executing {tool_name}...", "processing")
            
        try:
            # Run tool
            result = await tool.run(**kwargs)
            
            # Report End
            if self.status_callback:
                await self.status_callback(f"Finished {tool_name}.", "processing")
                
            return result
        except Exception as e:
            if self.status_callback:
                await self.status_callback(f"Error in {tool_name}: {str(e)}", "error")
            raise e

    async def chat_with_tools(
        self, 
        system_prompt: str,
        message_history: List[Message],
        tool_definitions: List = None,
        tool_functions: dict = None,
        api_key: Optional[str] = None,
        tool_context: dict = None
    ) -> str:
        """
        Core LLM Loop - Ported from BaseAgent.
        Stateless: Takes history as input, returns final response string.
        """
        # Resolve API Key: Argument > Context
        resolved_key = api_key or self.context.get("api_key")
        
        print(f"[{self.__class__.__name__}] Initializing LLM. Key present: {bool(resolved_key)}")

        if not self.llm or resolved_key:
            try:
                self.llm = get_provider(api_key=resolved_key)
            except Exception as e:
                print(f"[BaseNode] ❌ Failed to initialize LLM: {e}")
                traceback.print_exc()
                if not self.llm: 
                    return f"Error: AI Provider configuration failed. {str(e)}"

        # --- Inject current time ---
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S (%A)')
        time_context = f"\n\n## Current Context\n- **Current Date & Time**: {current_time_str}\n"

        # Format messages
        llm_messages = [m.to_llm_message() for m in message_history]
        effective_system_prompt = system_prompt + time_context

        # Get preferred model from context
        preferred_model = self.context.get("preferred_model")

        # Call LLM
        try:
            t0 = time.time()
            messages = self.llm.format_messages(effective_system_prompt, llm_messages)
            
            # --- Handle Class-Based Tools ---
            # If explicit tool_definitions are passed (even []), use them.
            # Otherwise, fall back to self.tools if present.
            final_tool_defs = tool_definitions
            final_tool_funcs = tool_functions
            
            if tool_definitions is None:
                if self.tools:
                    print(f"[{self.__class__.__name__}] Using {len(self.tools)} class-based tools.")
                    final_tool_defs = [tool.declaration() for tool in self.tools]
                    # Wrap tool.run in _execute_tool with an explicit async function
                    final_tool_funcs = {}
                    for tool in self.tools:
                        async def wrapper(t=tool, **kwargs):
                            return await self._execute_tool(t, **kwargs)
                        final_tool_funcs[tool.name] = wrapper
                else:
                    final_tool_defs = []
                    final_tool_funcs = {}
            elif tool_functions is None:
                # If definitions were passed but no functions, check if we can map from self.tools
                final_tool_funcs = {}
                for tool in self.tools:
                    async def wrapper(t=tool, **kwargs):
                        return await self._execute_tool(t, **kwargs)
                    final_tool_funcs[tool.name] = wrapper

            # Extract attached files from the LAST user message only (current request)
            # Old history files are not re-sent - they were processed in their original request
            current_attached_files = None
            for msg in reversed(message_history):
                if msg.role.value == "user":
                    if msg.attached_files and msg.attached_files != []:
                        current_attached_files = msg.attached_files
                    break

            response = await self.llm.complete_async(
                messages, 
                tool_context=tool_context or {},
                tool_definitions=final_tool_defs,
                tool_functions=final_tool_funcs,
                preferred_model=preferred_model,
                attached_files=current_attached_files if current_attached_files else None
            )
            print(f"[{self.__class__.__name__}/Timing] LLM complete: {time.time()-t0:.2f}s")
            
            # Return full response to include tool_calls metadata
            return response
            
        except Exception as e:
            print(f"[{self.__class__.__name__}] LLM Error: {e}")
            traceback.print_exc()
            # Return a minimal response object on error
            from llm.base_provider import CompletionResponse
            return CompletionResponse(content=f"Error: {str(e)}", model="error")

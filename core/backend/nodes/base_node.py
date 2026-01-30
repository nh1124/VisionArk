from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import time
import traceback
from datetime import datetime
from llm import get_provider
from llm.reasoning_engine import ReasoningEngine
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
        
    async def load_system_prompt(self, role_name: Optional[str] = None, components: Optional[List[str]] = None) -> str:
        """
        Load the system prompt from components, database (Node), or backend assets.
        Components + Role Specific + Dynamic Tool Descriptions.
        """
        from utils.paths import get_prompts_dir
        from models.database import AsyncSessionLocal, Node
        from sqlalchemy import select
        
        prompts_dir = get_prompts_dir()
        
        # 1. Load Components (Modular)
        component_texts = []
        if components:
            for comp in components:
                comp_path = prompts_dir / "components" / f"{comp}.md"
                try:
                    if comp_path.exists():
                        component_texts.append(comp_path.read_text(encoding='utf-8'))
                    else:
                        print(f"[BaseNode] Warning: Component {comp} not found at {comp_path}")
                except Exception as e:
                    print(f"[BaseNode] Error loading component {comp}: {e}")
        
        # Fallback to global if no components provided (Backward Compatibility)
        if not component_texts and not components:
            global_path = prompts_dir / "system" / "global.md"
            try:
                if global_path.exists():
                    component_texts.append(global_path.read_text(encoding='utf-8'))
                else:
                    component_texts.append("You are a helpful AI assistant.")
            except Exception as e:
                print(f"[BaseNode] Error loading global prompt: {e}")

        # 2. Load Role Specifics (DB Profile first, then Fallback to static Markdown)
        role_text = ""
        if role_name:
            # Try DB first
            async with AsyncSessionLocal() as db:
                try:
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
                        role_text = profile.system_prompt
                except Exception as e:
                    print(f"[BaseNode] DB error fetching role prompt: {e}")

            # Fallback to Markdown
            if not role_text:
                role_path = prompts_dir / "roles" / f"{role_name}.md"
                try:
                    if role_path.exists():
                        role_text = role_path.read_text(encoding='utf-8')
                except Exception as e:
                    print(f"[BaseNode] Error loading role prompt: {e}")
        
        # 3. Dynamic Tool Descriptions
        tool_text = ""
        # Native AI Tool calling already handles declarations, but text-based 
        # descriptions provide a vital reference for the agent to recognize capabilities.
        if self.tools:
            tool_text = "\n## Available Tools (Native Functions)\n"
            for tool in self.tools:
                decl = tool.declaration()
                name = decl.get("name")
                desc = decl.get("description")
                tool_text += f"- `{name}`: {desc}\n"
        
        # 4. Agent Skills (Dynamically injected instructions)
        skill_text = ""
        node_id = self.context.get("node_id")
        if node_id:
            try:
                from services.skill_service import SkillService
                async with AsyncSessionLocal() as db:
                    skill_text = await SkillService.inject_skills_to_prompt(db, node_id, "")
            except Exception as se:
                print(f"[BaseNode] Error loading skills: {se}")

        # 5. Combine
        all_parts = component_texts + [role_text, skill_text, tool_text]
        parts = [p for p in all_parts if p]
        return "\n\n".join(parts) if parts else "You are a helpful AI assistant."
    
    async def on_enter(self):
        """
        Standardized context hydration:
        1. Ensure DB session.
        2. Resolve User API Key & Settings.
        3. Load Project Metadata if project_id is present.
        """
        from models.database import get_async_engine, get_async_session_maker
        from sqlalchemy import select
        
        # 1. Ensure Session
        self._owns_session = False
        if not self.context.get("db_session"):
            engine = get_async_engine()
            session_maker = get_async_session_maker(engine)
            self.context["db_session"] = session_maker()
            self._owns_session = True
        
        session = self.context["db_session"]
        
        # 0. Set Node Identity in context for tools
        if hasattr(self, "node") and self.node:
            self.context["node_id"] = self.node.id
        
        # 2. Resolve API Key & Preferred Model
        if not self.context.get("api_key"):
            from tools.utils import get_user_api_key
            self.context["api_key"] = await get_user_api_key(self.user_id, session)
            
        if not self.context.get("user_settings") or not self.context.get("preferred_model"):
            from models.database import UserSettings
            res = await session.execute(select(UserSettings).filter(UserSettings.user_id == self.user_id))
            settings = res.scalars().first()
            if settings:
                self.context["user_settings"] = settings.general_settings or {}
                if settings.ai_config:
                    self.context["preferred_model"] = settings.ai_config.get("default_model")

        # 4. Dynamic Integration Tools
        try:
            from tools import get_integration_tools
            integration_tools = await get_integration_tools(self.user_id, session)
            existing_names = {t.name for t in self.tools}
            for it in integration_tools:
                if it.name not in existing_names:
                    self.tools.append(it)
        except Exception as e:
            print(f"[BaseNode] Warning: Failed to load integration tools: {e}")

        # 3. Load Node Identity (for display_name/description if missing)
        # Often provided by registry, but good to have a backup for project-less nodes

    @abstractmethod
    async def on_execute(self, message: str) -> Any:
        """Main logic (LLM or Command). Must be overridden."""
        raise NotImplementedError

    async def on_exit(self, result: Any):
        """Hook for side effects (Advocate, saving logs)."""
        pass

    async def process(self, message: str) -> Any:
        """
        Public entry point that enforces the lifecycle hooks:
        on_enter -> on_execute -> on_exit.
        """
        try:
            print(f"▶️ [{self.__class__.__name__}] Starting process | Message: {message[:100]}...")
            await self.on_enter()
            result = await self.on_execute(message)
            await self.on_exit(result)
            print(f"✅ [{self.__class__.__name__}] Finished process.")
            return result
        finally:
            # Cleanup session if we created it
            if getattr(self, "_owns_session", False):
                session = self.context.get("db_session")
                if session:
                    await session.close()
                    self.context["db_session"] = None

    async def _execute_tool(self, tool, **kwargs):
        """
        Execute a tool with callback injection and status reporting.
        """
        tool_name = tool.name
        
        # Inject context
        tool.context = self.context
        
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
        tool_context: dict = None,
        task_id: Optional[str] = None
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

        # --- Inject current time and localization ---
        import pytz
        user_settings = self.context.get("user_settings", {})
        language = user_settings.get("language", "en")
        timezone_str = user_settings.get("timezone", "UTC")
        location = user_settings.get("location", "Unknown")

        try:
            tz = pytz.timezone(timezone_str)
            local_now = datetime.now(tz)
        except Exception:
            local_now = datetime.now()
            timezone_str = "UTC"

        current_time_str = local_now.strftime('%Y-%m-%d %H:%M:%S (%A)')
        
        time_context = f"\n\n## Current Context\n- **Current Local Time**: {current_time_str}\n"
        time_context += f"- **Timezone**: {timezone_str}\n"
        time_context += f"- **Language Preference**: {language}\n"
        if location:
            time_context += f"- **Location**: {location}\n"

        # Prepare system instruction: System Prompt + Time context
        effective_system_prompt = system_prompt + time_context
        messages = list(message_history)

        # Get preferred model from context
        preferred_model = self.context.get("preferred_model")
        
        # Call LLM
        try:
            t0 = time.time()
            print(f"💬 [{self.__class__.__name__}] LLM Call starting (preferred_model: {preferred_model})...")
            
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
                msg_role = msg.role.value if hasattr(msg.role, 'value') else msg.role
                if msg_role == "user":
                    if msg.attached_files and msg.attached_files != []:
                        current_attached_files = msg.attached_files
                    break

            # Use Reasoning Engine to orchestrate turns
            engine = ReasoningEngine(self.llm)
            response = await engine.execute_async(
                messages, 
                system_instruction=effective_system_prompt,
                tool_definitions=final_tool_defs,
                tool_functions=final_tool_funcs,
                tool_context=tool_context or {},
                preferred_model=preferred_model,
                attached_files=current_attached_files if current_attached_files else None,
                task_id=task_id or self.task_id
            )
            elapsed = time.time() - t0
            print(f"🏁 [{self.__class__.__name__}/Timing] Total chat_with_tools complete in {elapsed:.2f}s")
            
            # Return full response to include tool_calls metadata
            return response
            
        except Exception as e:
            print(f"[{self.__class__.__name__}] LLM Error: {e}")
            traceback.print_exc()
            # Return a minimal response object on error
            from llm.base_provider import CompletionResponse
            return CompletionResponse(content=f"Error: {str(e)}", model="error")

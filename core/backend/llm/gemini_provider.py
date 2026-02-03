"""
Gemini LLM Provider  
Supports Gemini 3 models with Function Calling using the new google-genai SDK
"""
from google.genai import Client, types
from typing import List, Optional, Any, Dict
import asyncio
import inspect
import json
import time
from .base_provider import BaseLLMProvider, CompletionResponse
from config import settings
from models.message import MessageRole, Message, ToolCall, SubMessage


import logging
import uuid
logger = logging.getLogger(__name__)

class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider with function calling support"""
    
    def __init__(self, model_name: str = "gemini-3-pro-preview", api_key: str = None, **kwargs):
        super().__init__(model_name, api_key, **kwargs)
        # Initialize the new SDK client
        if self.api_key:
             masked_key = f"{self.api_key[:4]}...{self.api_key[-4:]}" if len(self.api_key) > 8 else "SHORT_KEY"
             logger.info(f"Initializing Client with key: {masked_key}")
        else:
             logger.warning("Initializing Client with NO KEY")
             
        self.client = Client(api_key=self.api_key, http_options={'api_version': 'v1alpha', 'timeout': 600000})
        self.tools = []  # Store tools for function calling
    

    def set_tool_definitions(self, definitions: List[Dict], tool_functions: Dict = None):
        """Set tool definitions directly (dict format) with optional function map"""
        self._tool_definitions = definitions
        self._tool_functions = tool_functions or {}

    def _convert_schema(self, prop_schema: Dict) -> types.Schema:
        """Recursively convert JSON schema to Gemini Schema"""
        prop_type = prop_schema.get("type", "string").upper()
        
        # Map JSON schema types to Gemini types
        # Note: New SDK uses 'STRING' strings or enum values.
        
        # Prepare schema arguments
        schema_args = {
            "type": prop_type,
            "description": prop_schema.get("description", ""),
        }
        
        # Handle Array: items is mandatory for ARRAY type
        if prop_type == "ARRAY" and "items" in prop_schema:
            schema_args["items"] = self._convert_schema(prop_schema["items"])
            
        # Handle Object: properties and required
        if prop_type == "OBJECT" and "properties" in prop_schema:
            schema_args["properties"] = {
                k: self._convert_schema(v) for k, v in prop_schema["properties"].items()
            }
            if "required" in prop_schema:
                schema_args["required"] = prop_schema["required"]
                
        # Handle Enum
        if "enum" in prop_schema:
            schema_args["enum"] = prop_schema["enum"]
            
        return types.Schema(**schema_args)

    def _convert_dict_tools_to_gemini(self, definitions: List[Dict]) -> List[types.Tool]:
        """Convert dict-based tool definitions to Gemini Tool format"""
        function_declarations = []
        
        for defn in definitions:
            # Build parameters schema using recursive converter
            params = defn.get("parameters", {})
            schema = self._convert_schema(params)
            
            func_decl = types.FunctionDeclaration(
                name=defn["name"],
                description=defn.get("description", ""),
                parameters=schema
            )
            function_declarations.append(func_decl)
        
        return [types.Tool(function_declarations=function_declarations)]
    
    def _make_system_instruction(self, instruction: Optional[str]) -> Optional[types.Content]:
        """Convert a string system instruction into a Gemini Content object."""
        if not instruction:
            return None
        return types.Content(
            role="system",
            parts=[types.Part.from_text(text=instruction)]
        )

    def _prepare_history(self, messages: List[Message]) -> List[types.Content]:
        """
        Converts a list of Message objects into Gemini Native Content objects.
        """
        history = []
        
        for m in messages:
            role_val = getattr(m.role, "value", m.role)
            if role_val == MessageRole.SYSTEM.value:
                # Option A: Convert system message to a user message with a prefix in history
                # This ensures we don't break the SDK's role restrictions while preserving context
                history.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=f"**[SYSTEM NOTIFICATION]**:\n{m.content}")]
                ))
            elif role_val == MessageRole.USER.value:
                role = "user"
                parts = []
                
                # 1. Add multimodal files first (Gemini recommendation for context)
                if m.attached_files:
                    for attached_file in m.attached_files:
                        if hasattr(attached_file, 'gemini_file_uri') and attached_file.gemini_file_uri:
                            try:
                                parts.append(types.Part.from_uri(
                                    file_uri=attached_file.gemini_file_uri,
                                    mime_type=attached_file.file_type
                                ))
                            except Exception as e:
                                logger.error(f"[Gemini] Failed to add file part: {e}")

                # 2. Add text content
                if m.content:
                    parts.append(types.Part.from_text(text=m.content))
                    
                history.append(types.Content(role=role, parts=parts))
            elif role_val == MessageRole.ASSISTANT.value:
                # Iterate through SubMessages to extract thoughts and tool calls
                if m.sub_messages:
                    for sub in m.sub_messages:
                        # 1. Model turn (Thought + Function Call intents)
                        model_parts = []
                        if sub.content:
                            model_parts.append(types.Part.from_text(text=sub.content))
                        
                        if sub.tool_calls:
                            for tc in sub.tool_calls:
                                model_parts.append(types.Part.from_function_call(
                                    name=tc.name,
                                    args=tc.args or {}
                                ))
                        
                        if model_parts:
                            history.append(types.Content(role="model", parts=model_parts))
                            
                        # 2. Tool turn (Function Responses)
                        if sub.tool_calls:
                            tool_parts = []
                            for tc in sub.tool_calls:
                                tool_parts.append(types.Part.from_function_response(
                                    name=tc.name,
                                    response={'result': tc.result}
                                ))
                                
                                # --- MULTIMODAL ATTACHMENT PROCESSING ---
                                # Convert standardized attachments (from ToolResult) to native Gemini parts.
                                if hasattr(tc, 'attachments') and tc.attachments:
                                    unique_uris = {}
                                    for att in tc.attachments:
                                        # Standardized format (new) or backward compat check
                                        uri = None
                                        if att.get("type") == "gemini_file_uri":
                                            uri = att.get("value")
                                        elif "gemini_file_uri" in att: # backward compat for old DB records
                                            uri = att.get("gemini_file_uri")
                                            
                                        if uri:
                                            unique_uris[uri] = att.get("mime_type")
                                    
                                    for uri, mime in unique_uris.items():
                                        if uri and mime and mime != "application/octet-stream":
                                            tool_parts.append(types.Part.from_uri(file_uri=uri, mime_type=mime))
                            
                            if tool_parts:
                                history.append(types.Content(role="tool", parts=tool_parts))
                else:
                    # Fallback for simple message without sub-messages
                    model_parts = []
                    if m.content:
                        model_parts.append(types.Part.from_text(text=m.content))
                    if model_parts:
                        history.append(types.Content(role="model", parts=model_parts))
            else:
                logger.warning(f"Unknown message role: {m.role}")
        
        return history

    def _append_tool_results(self, history: List[types.Content], tool_calls: List[ToolCall]) -> List[types.Content]:
        """
        Appends tool results to the native Gemini history.
        """
        if not tool_calls:
            return history
            
        tool_parts = []
        for tc in tool_calls:
            if tc.result is not None:
                tool_parts.append(types.Part.from_function_response(
                    name=tc.name,
                    response={'result': tc.result}
                ))

                # --- MULTIMODAL ATTACHMENT PROCESSING ---
                # Convert standardized attachments (from ToolResult) to native Gemini parts.
                if hasattr(tc, 'attachments') and tc.attachments:
                    unique_uris = {}
                    for att in tc.attachments:
                        uri = None
                        if att.get("type") == "gemini_file_uri":
                            uri = att.get("value")
                        elif "gemini_file_uri" in att:
                            uri = att.get("gemini_file_uri")
                            
                        if uri:
                            unique_uris[uri] = att.get("mime_type")
                    
                    for uri, mime in unique_uris.items():
                        if uri and mime and mime != "application/octet-stream":
                            tool_parts.append(types.Part.from_uri(file_uri=uri, mime_type=mime))
        
        if tool_parts:
            # Create a copy of history to avoid side effects if needed, 
            # though in reasoning loop we actually want to mutate or return a new one.
            new_history = list(history)
            new_history.append(types.Content(role="tool", parts=tool_parts))
            return new_history
            
        return history


    async def complete_async(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        preferred_model: Optional[str] = None,
        tool_definitions: List = None,
        native_context: Optional[Any] = None,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> CompletionResponse:
        """Asynchronously generate a single completion turn using Gemini."""
        model_name = preferred_model or self.model_name
        
        # 1. Prepare History & Config
        if native_context:
            logger.info(f"🚀 [Gemini] Using native_context pass-through ({len(native_context)} turns)")
            history = list(native_context)
            # Check for incremental tool results to append
            incremental_tool_calls = kwargs.get('incremental_tool_calls')
            if incremental_tool_calls:
                history = self._append_tool_results(history, incremental_tool_calls)
            
            # Resolve system instruction for config (even if history is provided)
            # Note: For Gemini, system instruction is usually in generation_config.
            # If native_context is used, we assume system instruction was already set or we re-pass it.
            system_instruction_content = self._make_system_instruction(system_instruction)
        else:
            history = self._prepare_history(messages)
            system_instruction_content = self._make_system_instruction(system_instruction)
        
        if tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(tool_definitions)
        elif hasattr(self, '_tool_definitions') and self._tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(self._tool_definitions)
        else:
            tools_for_model = []
        
        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools_for_model if tools_for_model else None,
            system_instruction=system_instruction_content,
            response_mime_type="application/json" if response_format else None,
            response_schema=response_format
        )
        
        if tools_for_model and hasattr(tools_for_model[0], 'function_declarations') and tools_for_model[0].function_declarations:
            generation_config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        # 2. Single Turn API Call
        try:
            t0 = time.time()
            logger.info(f"📡 [Gemini] Calling generate_content for model {model_name} (History: {len(history)} turns, Tools: {len(tool_definitions) if tool_definitions else 0})")
            response = await self.client.aio.models.generate_content(
                model=model_name,
                contents=history,
                config=generation_config
            )
            elapsed = time.time() - t0
            logger.info(f"✅ [Gemini] Generation complete in {elapsed:.2f}s")
        except Exception as e:
            logger.error(f"[Gemini] Async Generation error: {e}")
            raise
        
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            return CompletionResponse(content="", model=model_name, usage=None)
            
        model_content = response.candidates[0].content
        function_calls = [p.function_call for p in model_content.parts if p.function_call]
        text_parts = [p.text for p in model_content.parts if p.text]
        combined_text = "".join(text_parts).strip()

        # Construct ToolCall objects from intents
        intents = []
        for fc in function_calls:
            intents.append(ToolCall(name=fc.name, args=fc.args or {}))

        if intents:
            logger.info(f"🔮 [Gemini] Model generated {len(intents)} tool intents: {[i.name for i in intents]}")

        usage = None
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "candidates_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count
            }

        # Create a SubMessage for this turn
        step = SubMessage(
            sub_id=str(uuid.uuid4()),
            content=combined_text,
            tool_calls=intents
        )

        # Append the new model turn to history for optimization
        history.append(model_content)

        return CompletionResponse(
            content=combined_text,
            model=model_name,
            usage=usage,
            step=step,
            native_context=history
        )


    def complete(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        preferred_model: Optional[str] = None,
        tool_definitions: List = None,
        native_context: Optional[Any] = None,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate a single completion turn using Gemini."""
        model_name = preferred_model or self.model_name
        
        # 1. Prepare History & Config
        if native_context:
            logger.info(f"🚀 [Gemini] Using native_context pass-through ({len(native_context)} turns)")
            history = list(native_context)
            incremental_tool_calls = kwargs.get('incremental_tool_calls')
            if incremental_tool_calls:
                history = self._append_tool_results(history, incremental_tool_calls)
            system_instruction_content = self._make_system_instruction(system_instruction)
        else:
            history = self._prepare_history(messages)
            system_instruction_content = self._make_system_instruction(system_instruction)
        
        if tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(tool_definitions)
        elif hasattr(self, '_tool_definitions') and self._tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(self._tool_definitions)
        else:
            tools_for_model = []
        
        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools_for_model if tools_for_model else None,
            system_instruction=system_instruction_content,
            response_mime_type="application/json" if response_format else None,
            response_schema=response_format
        )
        
        if tools_for_model and hasattr(tools_for_model[0], 'function_declarations') and tools_for_model[0].function_declarations:
            generation_config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        # 2. Single Turn API Call
        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=history,
                config=generation_config
            )
        except Exception as e:
            logger.error(f"[Gemini] Generation error: {e}")
            raise
        
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            return CompletionResponse(content="", model=model_name, usage=None)
            
        model_content = response.candidates[0].content
        function_calls = [p.function_call for p in model_content.parts if p.function_call]
        text_parts = [p.text for p in model_content.parts if p.text]
        combined_text = "".join(text_parts).strip()

        # Construct ToolCall objects from intents
        intents = []
        for fc in function_calls:
            intents.append(ToolCall(name=fc.name, args=fc.args or {}))
            
        if intents:
            logger.info(f"🔮 [Gemini] Model generated {len(intents)} tool intents: {[i.name for i in intents]}")

        usage = None
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "candidates_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count
            }

        # Create a SubMessage for this turn
        step = SubMessage(
            sub_id=str(uuid.uuid4()),
            content=combined_text,
            tool_calls=intents
        )

        # Append the new model turn to history for optimization
        history.append(model_content)

        return CompletionResponse(
            content=combined_text,
            model=model_name,
            usage=usage,
            step=step,
            native_context=history
        )
    
    def embed(self, text: str) -> List[float]:
        """Generate embeddings using Gemini Embedding API"""
        result = self.client.models.embed_content(
            model="text-embedding-004",
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        )
        return result.embeddings[0].values
    
    def _extract_response_content(self, response) -> str:
        """
        Safely extracts text and other parts (like executable code) from response candidates.
        Silences the warning about non-text parts by manually iterating through them.
        """
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            return ""
        
        parts = response.candidates[0].content.parts
        full_text = []
        
        for part in parts:
            if part.text:
                full_text.append(part.text)
            elif part.executable_code:
                code = part.executable_code.code
                language = part.executable_code.language or "python"
                full_text.append(f"\\n```{language}\\n{code}\\n```\\n")
            elif part.code_execution_result:
                outcome = part.code_execution_result.outcome
                output = part.code_execution_result.output
                full_text.append(f"\\n> **Code Execution {outcome}**\\n> ```\\n> {output}\\n> ```\\n")
                
        return "".join(full_text).strip()
    
    async def upload_file(self, file_path: str, mime_type: str = None, display_name: str = None) -> Dict:
        """
        Upload a file to Gemini File API for multimodal processing.
        """
        from pathlib import Path
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            uploaded_file = await self.client.aio.files.upload(
                file=str(path),
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=display_name or path.name
                )
            )
            
            return {
                "file_uri": uploaded_file.uri,
                "file_name": uploaded_file.name,
                "display_name": display_name or path.name,
                "mime_type": uploaded_file.mime_type,
                "size_bytes": path.stat().st_size
            }
        except Exception as e:
            raise RuntimeError(f"Failed to upload file to Gemini: {str(e)}")
    
    def get_uploaded_file(self, file_name: str):
        """Retrieve a previously uploaded file"""
        return self.client.files.get(name=file_name)
    
    def complete_with_files(
        self,
        messages: List[Message],
        file_references: List[str],  # Gemini file URIs or names
        temperature: float = 0.7,
        preferred_model: str = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion with uploaded files included in context"""
        # Wrap references as objects compatible with _prepare_history
        class FileRef:
            def __init__(self, uri):
                self.gemini_file_uri = uri
                self.file_type = "image/jpeg" # Default to image for safety

        attached_files = [FileRef(ref) for ref in file_references]
        
        return self.complete(
            messages=messages,
            temperature=temperature,
            preferred_model=preferred_model,
            attached_files=attached_files,
            **kwargs
        )
    
    async def stream_chat_async(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_model: Optional[str] = None,
        attached_files: List = None,
        tool_definitions: List = None,
        tool_functions: dict = None,
        task_id: Optional[str] = None,
        **kwargs
    ):
        """Asynchronously stream chat events including status updates during function calling."""
        model_name = preferred_model or self.model_name
        
        # Helper: Status mapping
        status_map = {
            "search_knowledge": "Searching facts & memories...",
            "google_search": "Searching Google...",
            "create_task": "Adding task to schedule...",
            "get_lbs_schedule": "Checking workload...",
            "ask_node": lambda args: f"Messaging Node/Project: {args.get('target')}..."
        }

        # 1. Prepare History & Config
        history = self._prepare_history(messages)
        system_instruction_content = self._make_system_instruction(system_instruction)
        
        active_tool_functions = tool_functions or getattr(self, '_tool_functions', {})
        if tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(tool_definitions)
        elif hasattr(self, '_tool_definitions') and self._tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(self._tool_definitions)
        else:
            tools_for_model = []
        
        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools_for_model if tools_for_model else None,
            system_instruction=system_instruction_content,
            response_mime_type="application/json" if response_format else None,
            response_schema=response_format
        )
        
        if tools_for_model and hasattr(tools_for_model[0], 'function_declarations') and tools_for_model[0].function_declarations:
            generation_config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        turn_count = 0
        max_turns = settings.max_tool_turns
        accumulated_tool_results = []
        newly_generated_messages = []
        
        yield {"type": "status", "data": "Thinking..."}
        
        while max_turns is None or turn_count < max_turns:
            if task_id:
                from queue_system.manager import QueueManager
                manager = QueueManager()
                status_data = manager.get_status(task_id)
                if status_data and status_data.get("status") == "cancelled":
                    yield {"type": "status", "data": "Stopped by user."}
                    yield {
                        "type": "final_response",
                        "data": {
                            "content": "Task stopped by user.",
                            "usage": None,
                            "metadata": {"cancelled": True}
                        }
                    }
                    return

            turn_count += 1
            yield {"type": "status", "data": f"Thinking (Turn {turn_count})..."}
            
            try:
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=history,
                    config=generation_config
                )
                
                if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                    # If no content, it might be an empty response or an error, break the loop
                    break
                    
                model_content = response.candidates[0].content
                history.append(model_content)
                
                function_calls = [p.function_call for p in model_content.parts if p.function_call]
                combined_text = "".join([p.text for p in model_content.parts if p.text]).strip()

                # Record Model Turn
                current_tool_calls = []
                if function_calls:
                    current_tool_calls = [ToolCall(name=fc.name, args=fc.args) for fc in function_calls]
                
                if not function_calls:
                    # Final content
                    yield {"type": "content", "data": combined_text}
                    
                    # Record final turn
                    new_msg = Message(
                        role=MessageRole.ASSISTANT,
                        content=combined_text,
                        tool_calls=[]
                    )
                    newly_generated_messages.append(new_msg)

                    yield {
                        "type": "final_response", 
                        "data": {
                            "content": combined_text, 
                            "new_messages": newly_generated_messages
                        }
                    }
                    return

                # Execute tool calls
                tool_response_parts = []
                turn_tool_results = []
                
                tool_context = kwargs.get('tool_context') or {}
                for fc in function_calls:
                    # Status yield
                    mapped = status_map.get(fc.name, f"Executing: {fc.name}...")
                    status_text = mapped(fc.args) if callable(mapped) else mapped
                    yield {"type": "status", "data": status_text}
                    
                    tool_result, file_uri, mime_type = await self._execute_tool_async(
                        fc, active_tool_functions, tool_context
                    )
                    
                    res_entry = ToolCall(
                        name=fc.name,
                        args=fc.args or {},
                        result=tool_result,
                        is_success=not (tool_result.startswith("Error") or tool_result.startswith("Failed"))
                    )
                    accumulated_tool_results.append(res_entry)
                    turn_tool_results.append(res_entry)
                    
                    tool_response_parts.append(types.Part.from_function_response(
                        name=fc.name,
                        response={'result': tool_result}
                    ))

                    if file_uri and mime_type and mime_type != "application/octet-stream":
                        tool_response_parts.append(types.Part.from_uri(file_uri=file_uri, mime_type=mime_type))
                
                # Record Bundled Turn (Model Thought + Tool Execution)
                bundled_msg = Message(
                    role=MessageRole.ASSISTANT,
                    content=combined_text,
                    tool_calls=turn_tool_results
                )
                newly_generated_messages.append(bundled_msg)

                history.append(types.Content(role="tool", parts=tool_response_parts))
                yield {"type": "status", "data": "Synthesizing result..."}

            except Exception as e:
                logger.error(f"[Gemini] Stream chat error: {e}")
                yield {"type": "error", "data": str(e)}
                return

    def stream_chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_model: Optional[str] = None,
        attached_files: List = None,
        tool_definitions: List = None,
        tool_functions: dict = None,
        **kwargs
    ):
        """Synchronously stream chat events including status updates during function calling."""
        model_name = preferred_model or self.model_name
        
        # Helper: Status mapping
        status_map = {
            "search_knowledge": "Searching facts & memories...",
            "google_search": "Searching Google...",
            "create_task": "Adding task to schedule...",
            "get_lbs_schedule": "Checking workload...",
            "ask_node": lambda args: f"Messaging Node/Project: {args.get('target')}..."
        }

        # 1. Prepare History & Config
        history = self._prepare_history(messages)
        system_instruction_content = self._make_system_instruction(system_instruction)
        
        active_tool_functions = tool_functions or getattr(self, '_tool_functions', {})
        if tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(tool_definitions)
        elif hasattr(self, '_tool_definitions') and self._tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(self._tool_definitions)
        else:
            tools_for_model = []
        
        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools_for_model if tools_for_model else None,
            system_instruction=system_instruction_content,
            response_mime_type="application/json" if response_format else None,
            response_schema=response_format
        )
        
        if tools_for_model and hasattr(tools_for_model[0], 'function_declarations') and tools_for_model[0].function_declarations:
            generation_config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        turn_count = 0
        max_turns = settings.max_tool_turns
        accumulated_tool_results = []
        newly_generated_messages = []
        
        yield {"type": "status", "data": "Thinking..."}
        
        while max_turns is None or turn_count < max_turns:
            turn_count += 1
            yield {"type": "status", "data": f"Thinking (Turn {turn_count})..."}
            
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=history,
                    config=generation_config
                )
                
                if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                    # If no content, it might be an empty response or an error, break the loop
                    break
                    
                model_content = response.candidates[0].content
                history.append(model_content)
                
                function_calls = [p.function_call for p in model_content.parts if p.function_call]
                combined_text = "".join([p.text for p in model_content.parts if p.text]).strip()

                # Record Model Turn
                current_tool_calls = []
                if function_calls:
                    current_tool_calls = [ToolCall(name=fc.name, args=fc.args) for fc in function_calls]
                
                if not function_calls:
                    final_text = combined_text
                    yield {"type": "content", "data": final_text}
                    
                    # Record final turn
                    new_msg = Message(
                        role=MessageRole.ASSISTANT,
                        content=final_text,
                        tool_calls=[]
                    )
                    newly_generated_messages.append(new_msg)

                    yield {
                        "type": "final_response",
                        "data": {
                            "content": final_text,
                            "new_messages": newly_generated_messages
                        }
                    }
                    return
                
                tool_context = kwargs.get('tool_context') or {}
                tool_response_parts = []
                turn_tool_results = []
                for fc in function_calls:
                    # Status yield
                    mapped = status_map.get(fc.name, f"Executing: {fc.name}...")
                    status_text = mapped(fc.args) if callable(mapped) else mapped
                    yield {"type": "status", "data": status_text}
                    
                    tool_result, file_uri, mime_type = self._execute_tool_sync(
                        fc, active_tool_functions, tool_context
                    )
                    
                    res_entry = ToolCall(
                        name=fc.name,
                        args=fc.args or {},
                        result=tool_result,
                        is_success=not (tool_result.startswith("Error") or tool_result.startswith("Failed"))
                    )
                    accumulated_tool_results.append(res_entry)
                    turn_tool_results.append(res_entry)
                    
                    tool_response_parts.append(types.Part.from_function_response(
                        name=fc.name,
                        response={'result': tool_result}
                    ))

                    if file_uri and mime_type and mime_type != "application/octet-stream":
                        tool_response_parts.append(types.Part.from_uri(file_uri=file_uri, mime_type=mime_type))
                
                # Record Bundled Turn (Model Thought + Tool Execution)
                bundled_msg = Message(
                    role=MessageRole.ASSISTANT,
                    content=combined_text,
                    tool_calls=turn_tool_results
                )
                newly_generated_messages.append(bundled_msg)

                history.append(types.Content(role="tool", parts=tool_response_parts))
                yield {"type": "status", "data": "Synthesizing result..."}

            except Exception as e:
                logger.error(f"[Gemini] Stream chat error: {e}")
                yield {"type": "error", "data": str(e)}
                return

    def stream_complete(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Stream completion tokens as they are generated.
        Yields string chunks.
        """
        model_name = kwargs.get('preferred_model') or self.model_name
        history = self._prepare_history(messages)
        system_instruction_content = self._make_system_instruction(system_instruction)
        
        try:
            stream = self.client.models.generate_content_stream(
                model=model_name,
                contents=history,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    system_instruction=system_instruction_content
                )
            )
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"[Gemini] stream_complete error: {e}")
            yield f"Error: {str(e)}"

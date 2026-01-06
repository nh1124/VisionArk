"""
Gemini LLM Provider  
Supports Gemini 1.5 and 2.0 models with Function Calling using the new google-genai SDK
"""
from google.genai import Client, types
from typing import List, Optional, Any, Dict
from .base_provider import BaseLLMProvider, Message, CompletionResponse


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider with function calling support"""
    
    def __init__(self, model_name: str = "gemini-3-pro-preview", api_key: str = None, **kwargs):
        super().__init__(model_name, api_key, **kwargs)
        # Initialize the new SDK client
        self.client = Client(api_key=self.api_key, http_options={'api_version': 'v1alpha', 'timeout': 600000})
        self.tools = []  # Store tools for function calling
    
    def set_tools(self, tools: List[Any]):
        """Set tools for function calling (supports LangChain tools or dict definitions)"""
        self.tools = tools
        self._tool_definitions = None  # Will be converted lazily
    
    def set_tool_definitions(self, definitions: List[Dict], tool_functions: Dict = None):
        """Set tool definitions directly (dict format) with optional function map"""
        self._tool_definitions = definitions
        self._tool_functions = tool_functions or {}
        self.tools = []  # Clear LangChain tools
    
    def _convert_langchain_tools_to_gemini(self, tools: List[Any]) -> List[Dict]:
        """Convert LangChain tools to Gemini function declarations"""
        gemini_tools = []
        
        for tool in tools:
            # Get the Pydantic schema from the tool
            schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') and tool.args_schema else {}
            
            # Convert properties to Gemini format
            # Gemini expects just properties and required, not a full JSON schema
            gemini_params = {}
            
            if 'properties' in schema:
                # Convert each property
                for prop_name, prop_schema in schema['properties'].items():
                    gemini_prop = {
                        "type_": prop_schema.get("type", "string").upper(),  # STRING, NUMBER, etc.
                        "description": prop_schema.get("description", "")
                    }
                    gemini_params[prop_name] = gemini_prop
            
            function_declaration = {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": {
                    "type_": "OBJECT",
                    "properties": gemini_params,
                    "required": schema.get("required", [])
                }
            }
            
            gemini_tools.append(function_declaration)
        
        return gemini_tools
    
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
    
    def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_model: Optional[str] = None,
        attached_files: List = None,  # List of AttachedFile objects
        tool_definitions: List = None,  # Agent-level tool definitions (passed directly)
        tool_functions: dict = None,    # Agent-level tool functions (passed directly)
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using Gemini with optional function calling and file attachments"""
        # Determine model to use (per-request override or default)
        model_name = preferred_model or self.model_name
        
        # Build prompt from messages
        full_prompt = self._build_prompt(messages)
        
        # Build content parts for multimodal request
        content_parts = []
        
        # Add file parts first
        if attached_files:
            for attached_file in attached_files:
                if hasattr(attached_file, 'gemini_file_uri') and attached_file.gemini_file_uri:
                    try:
                        # New SDK uses Part.from_uri or similar
                        file_part = types.Part.from_uri(
                            file_uri=attached_file.gemini_file_uri,
                            mime_type=attached_file.file_type
                        )
                        content_parts.append(file_part)
                        print(f"[Gemini] Added file part: {attached_file.filename}")
                    except Exception as e:
                        print(f"[Gemini] Failed to add file part for {attached_file.filename}: {e}")
        
        # Add text prompt
        content_parts.append(types.Part.from_text(text=full_prompt))
        
        # 1. Prepare Tools
        active_tool_functions = tool_functions or getattr(self, '_tool_functions', {})
        
        # Use passed tools first (from agent level), fallback to stored tools
        if tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(tool_definitions)
        elif hasattr(self, '_tool_definitions') and self._tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(self._tool_definitions)
        elif self.tools:
            # LangChain conversion skipped for now
            tools_for_model = []
        else:
            tools_for_model = []
        
        # Generate config
        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools_for_model if tools_for_model else None,
        )
        
        # Only set ToolConfig if we have actual functions to call
        if tools_for_model and hasattr(tools_for_model[0], 'function_declarations') and tools_for_model[0].function_declarations:
            generation_config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO"
                )
            )

        # Initialize history for this request
        history = [
            types.Content(
                role="user",
                parts=content_parts
            )
        ]
        
        turn_count = 0
        max_turns = 30
        accumulated_tool_results = []  # List of {name, result, success} dicts
        
        while turn_count < max_turns:
            turn_count += 1
            
            # Generate response
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=history,
                    config=generation_config
                )
            except Exception as e:
                print(f"[Gemini] Generation error: {e}")
                if accumulated_tool_results:
                    return CompletionResponse(
                        content=f"Error during continuation: {str(e)}",
                        model=model_name,
                        usage=None,
                        tool_calls=accumulated_tool_results
                    )
                raise
            
            # Check if valid response
            if not response.candidates or not response.candidates[0].content.parts:
                break
                
            model_content = response.candidates[0].content
            history.append(model_content)
            
            # Extract all function calls in this turn
            function_calls = [p.function_call for p in model_content.parts if p.function_call]
            
            if not function_calls:
                # Final text response
                final_text = response.text
                
                # 3. Process Grounding Metadata (Search Citations)
                # Extract token usage
                usage = None
                if response.usage_metadata:
                    usage = {
                        "prompt_tokens": response.usage_metadata.prompt_token_count,
                        "candidates_tokens": response.usage_metadata.candidates_token_count,
                        "total_tokens": response.usage_metadata.total_token_count
                    }

                return CompletionResponse(
                    content=final_text,
                    model=model_name,
                    usage=usage,
                    tool_calls=accumulated_tool_results if accumulated_tool_results else None
                )
            
            # Execute all tool calls in parallel (simulated sequentially here)
            tool_response_parts = []
            
            for fc in function_calls:
                function_name = fc.name
                function_args = fc.args
                
                print(f"[Gemini] Executing function: {function_name}")
                
                # Find and execute the matching tool function
                tool_result = None
                
                # Use passed tool functions (from agent), fallback to stored ones
                if function_name in active_tool_functions:
                    try:
                        import inspect
                        
                        # Get execution context from kwargs
                        tool_context = kwargs.get('tool_context') or {}
                        func = active_tool_functions[function_name]
                        
                        # Get the function's signature to know what parameters it accepts
                        sig = inspect.signature(func)
                        accepted_params = set(sig.parameters.keys())
                        
                        # Merge function args with only the injected context that the function accepts
                        full_args = {**function_args}
                        injected_keys = []
                        for key in ['session', 'user_id', 'node_id', 'node_type', 'spoke_name', 'context_name', 'meta_info']:
                            if key in tool_context and key in accepted_params:
                                full_args[key] = tool_context[key]
                                injected_keys.append(key)
                        
                        if injected_keys:
                            print(f"[Gemini] Injected context keys: {', '.join(injected_keys)}")
                        
                        # Safety check: log if mandatory params (from sig) are missing in full_args
                        missing_from_call = [p for p, param in sig.parameters.items() 
                                           if param.default == inspect.Parameter.empty 
                                           and p not in full_args 
                                           and p not in ['kwargs', 'args']]
                        if missing_from_call:
                            print(f"[Gemini] WARNING: Missing mandatory params for {function_name}: {missing_from_call}")
                        
                        result = func(**full_args)
                        
                        # Handle ToolResult objects
                        if hasattr(result, 'to_dict'):
                            tool_result = result.message
                        else:
                            tool_result = str(result)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        tool_result = f"Error executing {function_name}: {str(e)}"
                
                if tool_result is None:
                    tool_result = f"Function {function_name} not found"
                
                # Accumulate structured tool result
                is_success = not (tool_result.startswith("Error") or tool_result.startswith("Failed"))
                accumulated_tool_results.append({
                    "name": function_name,
                    "result": tool_result,
                    "success": is_success
                })
                
                # Add to response parts for Gemini (New SDK format)
                tool_response_parts.append(types.Part.from_function_response(
                    name=function_name,
                    response={'result': tool_result}
                ))
            
            # Add tool responses to history (role is 'tool' in new SDK)
            history.append(types.Content(
                role="tool",
                parts=tool_response_parts
            ))
            
        # If we exit loop due to turn count
        final_content = ""
        if turn_count >= max_turns:
            final_content = "(Reached maximum reasoning turns)"
            
        return CompletionResponse(
            content=final_content,
            model=model_name,
            usage={"total_turns": turn_count},
            tool_calls=accumulated_tool_results if accumulated_tool_results else None
        )
    
    def embed(self, text: str) -> List[float]:
        """Generate embeddings using Gemini Embedding API"""
        result = self.client.models.embed_content(
            model="text-embedding-004",
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        )
        return result.embeddings[0].values
    
    def upload_file(self, file_path: str, mime_type: str = None, display_name: str = None) -> Dict:
        """
        Upload a file to Gemini File API for multimodal processing.
        """
        from pathlib import Path
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            uploaded_file = self.client.files.upload(
                path=str(path),
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
        model_name = preferred_model or self.model_name
        
        # Build content parts with files
        content_parts = []
        
        # Add files first
        for file_ref in file_references:
            try:
                # In new SDK, we can use Part.from_uri
                content_parts.append(types.Part.from_uri(file_uri=file_ref, mime_type=None))
            except Exception as e:
                print(f"[Gemini] Warning: Could not retrieve file {file_ref}: {e}")
        
        # Add text prompt  
        full_prompt = self._build_prompt(messages)
        content_parts.append(types.Part.from_text(text=full_prompt))
        
        response = self.client.models.generate_content(
            model=model_name,
            contents=[types.Content(role='user', parts=content_parts)],
            config=types.GenerateContentConfig(temperature=temperature)
        )
        
        return CompletionResponse(
            content=response.text,
            model=model_name,
            usage=None
        )
    
    def stream_complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Stream completion tokens as they are generated.
        Yields string chunks.
        """
        model_name = kwargs.get('preferred_model') or self.model_name
        full_prompt = self._build_prompt(messages)
        
        try:
            stream = self.client.models.generate_content_stream(
                model=model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(temperature=temperature)
            )
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            print(f"[Gemini] stream_complete error: {e}")
            yield f"Error: {str(e)}"

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
        """
        Stream chat events including status updates during function calling.
        """
        model_name = preferred_model or self.model_name
        full_prompt = self._build_prompt(messages)
        content_parts = []
        
        if attached_files:
            for attached_file in attached_files:
                if hasattr(attached_file, 'gemini_file_uri') and attached_file.gemini_file_uri:
                    try:
                        file_part = types.Part.from_uri(
                            file_uri=attached_file.gemini_file_uri,
                            mime_type=attached_file.file_type
                        )
                        content_parts.append(file_part)
                    except Exception as e:
                        print(f"[Gemini] Failed to add file part: {e}")
        
        content_parts.append(types.Part.from_text(text=full_prompt))
        
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
        )
        
        if tools_for_model and hasattr(tools_for_model[0], 'function_declarations') and tools_for_model[0].function_declarations:
            generation_config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        history = [types.Content(role="user", parts=content_parts)]
        turn_count = 0
        max_turns = 30
        accumulated_tool_results = []
        
        yield {"type": "status", "data": "Thinking..."}
        
        while turn_count < max_turns:
            turn_count += 1
            yield {"type": "status", "data": f"Thinking (Turn {turn_count})..."}
            
            try:
                # Use generate_content instead of generate_content_stream for stability
                # This aligns with the stable complete() method
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=history,
                    config=generation_config
                )
                
                # Check if valid response
                if not response.candidates or not response.candidates[0].content.parts:
                    break
                    
                model_content = response.candidates[0].content
                history.append(model_content)
                
                # Extract all function calls in this turn
                function_calls = [p.function_call for p in model_content.parts if p.function_call]
                
                if not function_calls:
                    # Final response reached
                    final_text = response.text
                    yield {"type": "content", "data": final_text}
                    
                    yield {
                        "type": "final_response",
                        "data": {
                            "content": final_text,
                            "tool_calls": accumulated_tool_results,
                            "usage": None # Usage can be added if needed
                        }
                    }
                    return
                
                # Process tool calls
                tool_response_parts = []
                for fc in function_calls:
                    function_name = fc.name
                    function_args = fc.args
                    
                    # Emit status update for the tool call
                    status_msg = f"Executing: {function_name}..."
                    if function_name == "search_knowledge": status_msg = "Searching facts & memories..."
                    elif function_name == "google_search": status_msg = "Searching Google..."
                    elif function_name == "create_task": status_msg = "Adding task to schedule..."
                    elif function_name == "get_lbs_schedule": status_msg = "Checking workload..."
                    elif function_name == "ask_spoke": status_msg = f"Messaging Spoke: {function_args.get('spoke_name')}..."
                    
                    yield {"type": "status", "data": status_msg}
                    
                    tool_result = None
                    if function_name in active_tool_functions:
                        try:
                            import inspect
                            tool_context = kwargs.get('tool_context') or {}
                            func = active_tool_functions[function_name]
                            sig = inspect.signature(func)
                            accepted_params = set(sig.parameters.keys())
                            
                            full_args = {**function_args}
                            for key in ['session', 'user_id', 'node_id', 'node_type', 'spoke_name', 'context_name', 'meta_info']:
                                if key in tool_context and key in accepted_params:
                                    full_args[key] = tool_context[key]
                            
                            result = func(**full_args)
                            if hasattr(result, 'to_dict'):
                                tool_result = result.message
                            else:
                                tool_result = str(result)
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            tool_result = f"Error executing {function_name}: {str(e)}"
                    
                    if tool_result is None:
                        tool_result = f"Function {function_name} not found"
                    
                    accumulated_tool_results.append({
                        "name": function_name,
                        "result": tool_result,
                        "success": not (tool_result.startswith("Error") or tool_result.startswith("Failed"))
                    })
                    
                    tool_response_parts.append(types.Part.from_function_response(
                        name=function_name,
                        response={'result': tool_result}
                    ))
                
                # Add tool responses to history for next turn
                history.append(types.Content(role="tool", parts=tool_response_parts))
                yield {"type": "status", "data": "Synthesizing result..."}

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield {"type": "error", "data": str(e)}
                return

    def _build_prompt(self, messages: List[Message]) -> str:
        """Convert Message list to Gemini prompt format"""
        prompt_parts = []
        for msg in messages:
            if msg.role == "system":
                prompt_parts.append(f"System: {msg.content}\n\n")
            elif msg.role == "user":
                prompt_parts.append(f"User: {msg.content}\n\n")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}\n\n")
        return "".join(prompt_parts)

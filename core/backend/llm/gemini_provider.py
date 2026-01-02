"""
Gemini LLM Provider  
Supports Gemini 1.5 and 2.0 models with Function Calling
"""
import google.generativeai as genai
from typing import List, Optional, Any, Dict
from .base_provider import BaseLLMProvider, Message, CompletionResponse


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider with function calling support"""
    
    def __init__(self, model_name: str = "gemini-2.5-flash-lite", api_key: str = None, **kwargs):
        super().__init__(model_name, api_key, **kwargs)
        genai.configure(api_key=self.api_key)
        self.model = None  # Created with tools in complete()
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
    
    def _convert_schema(self, prop_schema: Dict) -> genai.protos.Schema:
        """Recursively convert JSON schema to Gemini Protocol Buffer schema"""
        prop_type = prop_schema.get("type", "string").upper()
        
        # Map JSON schema types to Gemini types
        type_map = {
            "STRING": genai.protos.Type.STRING,
            "NUMBER": genai.protos.Type.NUMBER,
            "INTEGER": genai.protos.Type.INTEGER,
            "BOOLEAN": genai.protos.Type.BOOLEAN,
            "ARRAY": genai.protos.Type.ARRAY,
            "OBJECT": genai.protos.Type.OBJECT,
        }
        
        genai_type = type_map.get(prop_type, genai.protos.Type.STRING)
        
        # Prepare schema arguments
        schema_args = {
            "type_": genai_type,
            "description": prop_schema.get("description", ""),
        }
        
        # Handle Array: items is mandatory for ARRAY type
        if genai_type == genai.protos.Type.ARRAY and "items" in prop_schema:
            schema_args["items"] = self._convert_schema(prop_schema["items"])
            
        # Handle Object: properties and required
        if genai_type == genai.protos.Type.OBJECT and "properties" in prop_schema:
            schema_args["properties"] = {
                k: self._convert_schema(v) for k, v in prop_schema["properties"].items()
            }
            if "required" in prop_schema:
                schema_args["required"] = prop_schema["required"]
                
        # Handle Enum
        if "enum" in prop_schema:
            schema_args["enum"] = prop_schema["enum"]
            
        return genai.protos.Schema(**schema_args)

    def _convert_dict_tools_to_gemini(self, definitions: List[Dict]) -> List[genai.protos.Tool]:
        """Convert dict-based tool definitions to Gemini Tool format"""
        function_declarations = []
        
        for defn in definitions:
            # Build parameters schema using recursive converter
            params = defn.get("parameters", {})
            schema = self._convert_schema(params)
            
            func_decl = genai.protos.FunctionDeclaration(
                name=defn["name"],
                description=defn.get("description", ""),
                parameters=schema
            )
            function_declarations.append(func_decl)
        
        return [genai.protos.Tool(function_declarations=function_declarations)]
    
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
        
        # Add file parts first (Gemini recommends files before text)
        if attached_files:
            for attached_file in attached_files:
                if hasattr(attached_file, 'to_gemini_part') and attached_file.has_gemini_reference():
                    try:
                        file_part = attached_file.to_gemini_part()
                        if file_part:
                            content_parts.append(file_part)
                            print(f"[Gemini] Added file part: {attached_file.filename}")
                    except Exception as e:
                        print(f"[Gemini] Failed to add file part for {attached_file.filename}: {e}")
        
        # Add text prompt
        content_parts.append(full_prompt)
        
        # Generate config
        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens
        
        # Create model with tools if available
        # Priority: passed tools > stored tools
        tools_for_model = None
        active_tool_functions = tool_functions or getattr(self, '_tool_functions', {})
        
        # Use passed tools first (from agent level), fallback to stored tools
        if tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(tool_definitions)
        elif hasattr(self, '_tool_definitions') and self._tool_definitions:
            tools_for_model = self._convert_dict_tools_to_gemini(self._tool_definitions)
        elif self.tools:
            gemini_tool_declarations = self._convert_langchain_tools_to_gemini(self.tools)
            tools_for_model = gemini_tool_declarations
        
        if self.api_key:
            # Ensure API key is configured for this specific call
            genai.configure(api_key=self.api_key)
        
        if tools_for_model:
            # Debug: Print what tools are being registered
            if tool_definitions:
                tool_names = [td.get('name', 'unknown') for td in tool_definitions]
                print(f"[Gemini DEBUG] Creating model with {len(tool_definitions)} tools: {tool_names[:5]}...")
            print(f"[Gemini DEBUG] tools_for_model type: {type(tools_for_model)}, len: {len(tools_for_model)}")
            model = genai.GenerativeModel(
                model_name,
                tools=tools_for_model
            )
            # Use AUTO mode to let model decide when to call functions
            tool_config = {"function_calling_config": {"mode": "AUTO"}}
        else:
            print(f"[Gemini DEBUG] Creating model WITHOUT tools")
            model = genai.GenerativeModel(model_name)
            tool_config = None
        
        # Prepare conversion to Gemini Content format for multi-turn
        def to_part(p):
            if isinstance(p, str):
                return genai.protos.Part(text=p)
            return p # Already a Part (e.g. from File API)

        # Initialize history for this request
        history = [
            genai.protos.Content(
                role="user",
                parts=[to_part(p) for p in (content_parts if content_parts else [full_prompt])]
            )
        ]
        
        turn_count = 0
        max_turns = 30
        accumulated_tool_results = []  # List of {name, result, success} dicts
        
        while turn_count < max_turns:
            turn_count += 1
            
            # Generate response
            try:
                response = model.generate_content(
                    history,
                    generation_config=generation_config,
                    tool_config=tool_config
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
                return CompletionResponse(
                    content=final_text,
                    model=model_name,
                    usage=None,
                    tool_calls=accumulated_tool_results if accumulated_tool_results else None
                )
            
            # Execute all tool calls in parallel (simulated sequentially here)
            tool_response_parts = []
            
            for fc in function_calls:
                function_name = fc.name
                function_args = dict(fc.args)
                
                print(f"[Gemini] Executing function: {function_name}")
                
                # Find and execute the matching tool function
                tool_result = None
                
                # Use passed tool functions (from agent), fallback to stored ones
                if function_name in active_tool_functions:
                    try:
                        import inspect
                        
                        # Get execution context from kwargs
                        tool_context = kwargs.get('tool_context', {})
                        func = active_tool_functions[function_name]
                        
                        # Get the function's signature to know what parameters it accepts
                        sig = inspect.signature(func)
                        accepted_params = set(sig.parameters.keys())
                        
                        # Merge function args with only the injected context that the function accepts
                        full_args = {**function_args}
                        for key in ['session', 'user_id', 'node_id', 'spoke_name', 'context_name']:
                            if key in tool_context and key in accepted_params:
                                full_args[key] = tool_context[key]
                        
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
                
                # Fallback to LangChain tools
                elif self.tools:
                    for tool in self.tools:
                        if tool.name == function_name:
                            try:
                                if hasattr(tool, 'func') and callable(tool.func):
                                    tool_result = tool.func(**function_args)
                                else:
                                    tool_result = tool.run(function_args)
                                break
                            except Exception as e:
                                import traceback
                                traceback.print_exc()
                                tool_result = f"Error executing {function_name}: {str(e)}"
                
                if tool_result is None:
                    tool_result = f"Function {function_name} not found"
                
                # Check if tool returned a multimodal reference (special logic)
                if isinstance(tool_result, str) and "__type__" in tool_result and "multimodal_ref" in tool_result:
                    try:
                        import ast
                        multimodal_data = ast.literal_eval(tool_result)
                        if multimodal_data.get("__type__") == "multimodal_ref":
                            file_uri = multimodal_data.get("file_uri")
                            file_name = multimodal_data.get("file_name")
                            mime_type = multimodal_data.get("mime_type")
                            
                            # Note: For multi-turn, we'll just treat the "thinking" as the result
                            # and let the model continue. We don't want to break the loop here.
                            # But since the previous code had specific return logic, we'll adapt it.
                            uploaded_file = genai.get_file(name=file_uri.split('/')[-1])
                            tool_result = f"Analyzed file '{file_name}' ({mime_type})."
                            # Add the actual file part to the NEXT model turn
                            # We can't easily inject it into the FunctionResponse part, 
                            # so we'll append it as a separate user turn or similar.
                            # For simplicity, we'll just log it.
                    except Exception:
                        pass
                
                # Accumulate structured tool result
                is_success = not (tool_result.startswith("Error") or tool_result.startswith("Failed"))
                accumulated_tool_results.append({
                    "name": function_name,
                    "result": tool_result,
                    "success": is_success
                })
                
                # Add to response parts for Gemini
                tool_response_parts.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=function_name,
                        response={'result': tool_result}
                    )
                ))
            
            # Add tool responses to history
            history.append(genai.protos.Content(
                role="function", # In protos, role should be "function"
                parts=tool_response_parts
            ))
            
        # If we exit loop due to turn count
        final_content = ""
        if turn_count >= max_turns:
            final_content = "(Reached maximum reasoning turns)"
            
        return CompletionResponse(
            content=final_content,
            model=model_name,
            usage=None,
            tool_calls=accumulated_tool_results if accumulated_tool_results else None
        )
        
        # Extract token usage
        total_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            total_tokens = getattr(response.usage_metadata, "total_token_count", 0)
        
        return CompletionResponse(
            content=response.text,
            model=self.model_name,
            usage={"total_tokens": total_tokens} if total_tokens > 0 else None
        )
    
    def embed(self, text: str) -> List[float]:
        """Generate embeddings using Gemini Embedding API"""
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        return result["embedding"]
    
    def upload_file(self, file_path: str, mime_type: str = None, display_name: str = None) -> Dict:
        """
        Upload a file to Gemini File API for multimodal processing.
        
        Args:
            file_path: Absolute path to the file
            mime_type: Optional MIME type (auto-detected if not provided)
            display_name: Optional display name for the file
            
        Returns:
            Dict with file_uri and file_name for later reference
        """
        import mimetypes
        from pathlib import Path
        
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Auto-detect MIME type if not provided
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(str(path))
            mime_type = mime_type or "application/octet-stream"
        
        # Display name defaults to filename
        if not display_name:
            display_name = path.name
        
        try:
            uploaded_file = genai.upload_file(
                path=str(path),
                mime_type=mime_type,
                display_name=display_name
            )
            
            return {
                "file_uri": uploaded_file.uri,
                "file_name": uploaded_file.name,
                "display_name": display_name,
                "mime_type": mime_type,
                "size_bytes": path.stat().st_size
            }
        except Exception as e:
            raise RuntimeError(f"Failed to upload file to Gemini: {str(e)}")
    
    def get_uploaded_file(self, file_name: str):
        """
        Retrieve a previously uploaded file by its Gemini file name.
        
        Args:
            file_name: The Gemini file name (not display name)
            
        Returns:
            Gemini file object
        """
        return genai.get_file(name=file_name)
    
    def complete_with_files(
        self,
        messages: List[Message],
        file_references: List[str],  # Gemini file URIs or names
        temperature: float = 0.7,
        preferred_model: str = None,
        **kwargs
    ) -> CompletionResponse:
        """
        Generate completion with uploaded files included in context.
        
        Args:
            messages: Conversation messages
            file_references: List of Gemini file URIs or names
            temperature: Temperature for generation
            preferred_model: Optional model override
            
        Returns:
            CompletionResponse with generated content
        """
        model_name = preferred_model or self.model_name
        
        # Build content parts with files
        content_parts = []
        
        # Add files first
        for file_ref in file_references:
            try:
                if file_ref.startswith("files/"):
                    # It's a file name
                    file_obj = self.get_uploaded_file(file_ref)
                else:
                    # Try to parse as URI to get name
                    file_name = file_ref.split("/")[-1]
                    file_obj = self.get_uploaded_file(f"files/{file_name}")
                content_parts.append(file_obj)
            except Exception as e:
                print(f"[Gemini] Warning: Could not retrieve file {file_ref}: {e}")
        
        # Add text prompt  
        full_prompt = self._build_prompt(messages)
        content_parts.append(full_prompt)
        
        generation_config = {"temperature": temperature}
        
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            content_parts,
            generation_config=generation_config
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
        """Stream completion tokens"""
        full_prompt = self._build_prompt(messages)
        
        generation_config = {
            "temperature": temperature,
        }
        
        # Use model with or without tools
        if self.tools:
            gemini_tool_declarations = self._convert_langchain_tools_to_gemini(self.tools)
            model = genai.GenerativeModel(
                self.model_name,
                tools=gemini_tool_declarations
            )
        else:
            model = genai.GenerativeModel(self.model_name)
        
        response = model.generate_content(
            full_prompt,
            generation_config=generation_config,
            stream=True
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
    
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

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
        """Set LangChain tools for function calling"""
        self.tools = tools
    
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
    
    def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_model: Optional[str] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using Gemini with optional function calling"""
        # Determine model to use (per-request override or default)
        model_name = preferred_model or self.model_name
        
        # Build prompt from messages
        full_prompt = self._build_prompt(messages)
        
        # Generate config
        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens
        
        # Create model with tools if available
        if self.tools:
            gemini_tool_declarations = self._convert_langchain_tools_to_gemini(self.tools)
            model = genai.GenerativeModel(
                model_name,
                tools=gemini_tool_declarations
            )
        else:
            model = genai.GenerativeModel(model_name)
        
        # Generate response
        response = model.generate_content(
            full_prompt,
            generation_config=generation_config
        )
        
        # Check if response contains function calls
        if response.candidates and response.candidates[0].content.parts:
            parts = response.candidates[0].content.parts
            
            # Check for function calls
            for part in parts:
                if hasattr(part, 'function_call') and part.function_call:
                    # Execute the function call
                    function_name = part.function_call.name
                    function_args = dict(part.function_call.args)
                    
                    # Find the matching tool
                    tool_result = None
                    for tool in self.tools:
                        if tool.name == function_name:
                            try:
                                # Call the underlying function directly
                                # The tool's func attribute is the bound function with spoke_name pre-filled
                                if hasattr(tool, 'func') and callable(tool.func):
                                    tool_result = tool.func(**function_args)
                                else:
                                    # Fallback to run method
                                    tool_result = tool.run(function_args)
                                break
                            except Exception as e:
                                import traceback
                                traceback.print_exc()
                                tool_result = f"Error executing {function_name}: {str(e)}"
                    
                    if tool_result is None:
                        tool_result = f"Function {function_name} not found"
                    
                    # Check if tool returned a multimodal reference
                    if isinstance(tool_result, str) and "__type__" in tool_result and "multimodal_ref" in tool_result:
                        try:
                            import ast
                            # Parse the dictionary string
                            multimodal_data = ast.literal_eval(tool_result)
                            
                            if multimodal_data.get("__type__") == "multimodal_ref":
                                file_uri = multimodal_data.get("file_uri")
                                file_name = multimodal_data.get("file_name")
                                mime_type = multimodal_data.get("mime_type")
                                
                                # Get the uploaded file from Gemini
                                uploaded_file = genai.get_file(name=file_uri.split('/')[-1])
                                
                                # Create a new prompt with the file
                                multimodal_prompt = [
                                    f"I uploaded the file '{file_name}' ({mime_type}). What can you tell me about it?",
                                    uploaded_file
                                ]
                                
                                # Make another API call with the file
                                multimodal_response = model.generate_content(
                                    multimodal_prompt,
                                    generation_config=generation_config
                                )
                                
                                return CompletionResponse(
                                    content=f"[File: {file_name}]\n\n{multimodal_response.text}",
                                    model=self.model_name,
                                    usage=None
                                )
                        except Exception as parse_error:
                            # If parsing fails, treat as regular text
                            pass
                    
                    # Return the tool result as content
                    return CompletionResponse(
                        content=f"[Tool Call: {function_name}]\n{tool_result}",
                        model=self.model_name,
                        usage=None
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

"""
Reasoning Engine
Orchestrates multi-turn LLM execution, tool calling, and history management.
Decouples execution logic from LLM connectivity.
"""
import asyncio
import time
import logging
import json
from typing import List, Optional, Dict, Any, Callable
from .base_provider import BaseLLMProvider, CompletionResponse
from models.message import Message, MessageRole, ToolCall
from config import settings

logger = logging.getLogger(__name__)

class ReasoningEngine:
    """
    Orchestrates the reasoning loop: LLM -> Tool -> LLM.
    """
    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def execute_async(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tool_definitions: List[Dict] = None,
        tool_functions: Dict[str, Callable] = None,
        tool_context: Dict[str, Any] = None,
        task_id: Optional[str] = None,
        status_callback: Optional[Callable[[str, str], Any]] = None,
        **kwargs
    ) -> CompletionResponse:
        """
        Asynchronously run the reasoning loop.
        """
        history = list(messages)
        newly_generated_messages = []
        turn_count = 0
        max_turns = settings.max_tool_turns
        
        # Resolve model name for reporting
        model_name = kwargs.get('preferred_model') or self.provider.model_name

        while max_turns is None or turn_count < max_turns:
            # Check for cancellation
            if task_id:
                try:
                    from queue_system.manager import QueueManager
                    manager = QueueManager()
                    status_data = manager.get_status(task_id)
                    if status_data and status_data.get("status") == "cancelled":
                        logger.info(f"🛑 [ReasoningEngine] Task {task_id} cancelled by user.")
                        return CompletionResponse(
                            content="Task stopped by user.",
                            model=model_name,
                            usage=None,
                            new_messages=newly_generated_messages
                        )
                except ImportError:
                    pass

            turn_count += 1
            if status_callback:
                await status_callback(f"Thinking (Turn {turn_count})...", "processing")
            
            logger.info(f"🔄 [ReasoningEngine] Entering Turn {turn_count}/{max_turns}...")
            
            # 1. Call LLM for a single turn
            response = await self.provider.complete_async(
                messages=history,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
                tool_definitions=tool_definitions,
                **kwargs
            )

            # If no content and no tool calls, break
            # In our rich Message model, we look at the last generated message
            if not response.new_messages:
                break
                
            last_msg = response.new_messages[-1]
            for m in response.new_messages:
                if not m.meta_info: m.meta_info = {}
                m.meta_info["turn_type"] = "thinking" if m.tool_calls else "final"
                
            newly_generated_messages.extend(response.new_messages)
            history.extend(response.new_messages)

            # 2. Check for tool calls
            tool_calls = last_msg.tool_calls
            if not tool_calls:
                # No more tools to call, we are done
                return CompletionResponse(
                    content=response.content,
                    model=response.model,
                    usage=response.usage,
                    new_messages=newly_generated_messages
                )

            # 3. Execute tools
            if not tool_functions:
                logger.warning(f"[ReasoningEngine] Model requested tools { [tc.name for tc in tool_calls] } but no functions provided.")
                break

            for tc in tool_calls:
                if tc.name in tool_functions:
                    if status_callback:
                        await status_callback(f"Executing {tc.name}...", "processing")
                    
                    try:
                        func = tool_functions[tc.name]
                        # Inject tool context if provided
                        full_kwargs = (tc.args or {}).copy()
                        if tool_context:
                            for k, v in tool_context.items():
                                if k not in full_kwargs:
                                    full_kwargs[k] = v
                                    
                        result = await func(**full_kwargs)
                                    
                        # Format result as JSON string if it's a dict/list to ensure valid JSON for frontend
                        if isinstance(result, (dict, list)):
                            tc.result = json.dumps(result)
                        else:
                            tc.result = str(result) if result is not None else ""
                        
                        tc.is_success = True
                    except Exception as e:
                        logger.error(f"[ReasoningEngine] Error executing {tc.name}: {e}")
                        tc.result = f"Error: {str(e)}"
                        tc.is_success = False
                else:
                    tc.result = f"Error: Function {tc.name} not found."
                    tc.is_success = False

            # Note: The history already contains the message with tool_calls.
            # Some providers (like Gemini) might need these results formatted specifically,
            # but since we appended the Message object to history, the NEXT call to 
            # provider.complete_async will handle the conversion of the history (including results)
            # into the provider's native format via its _prepare_history or similar logic.

        return CompletionResponse(
            content="(Reached maximum reasoning turns)" if (max_turns and turn_count >= max_turns) else response.content,
            model=model_name,
            usage={"total_turns": turn_count},
            new_messages=newly_generated_messages
        )

"""
Reasoning Engine
Orchestrates multi-turn LLM execution, tool calling, and history management.
Decouples execution logic from LLM connectivity.
"""
import asyncio
import time
import logging
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable
from .base_provider import BaseLLMProvider, CompletionResponse
from models.message import Message, MessageRole, ToolCall, SubMessage
from config import settings

logger = logging.getLogger(__name__)

class ReasoningEngine:
    """
    Orchestrates the reasoning loop: LLM -> Tool -> LLM.
    Uses the SubMessage thinking-step model for all turns.
    Returns a consolidated Message object.
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
    ) -> Message:
        """
        Asynchronously run the reasoning loop.
        Returns a single Message (ASSISTANT role) containing all intermediate SubMessages.
        """
        history = list(messages)
        steps = []
        turn_count = 0
        max_turns = settings.max_tool_turns
        
        # Optimization: Pass-through native context to avoid re-converting history
        current_native_context = None
        last_tool_calls = None
        
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
                        print(f"🛑 [ReasoningEngine] Task {task_id} cancelled by user.")
                        return Message(
                            role=MessageRole.ASSISTANT,
                            content="Task stopped by user.",
                            sub_messages=steps,
                            meta_info={"cancelled": True, "model": model_name}
                        )
                except ImportError:
                    pass

            turn_count += 1
            if status_callback:
                await status_callback(f"Thinking (Turn {turn_count})...", "processing")
            
            print(f"🔄 [ReasoningEngine] Entering Turn {turn_count}/{max_turns if max_turns else '∞'}...")
            
            # 1. Call LLM for a single turn (Thinking Step)
            # Optimization: Pass native_context if available to skip conversion
            response = await self.provider.complete_async(
                messages=history,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
                tool_definitions=tool_definitions,
                native_context=current_native_context,
                incremental_tool_calls=last_tool_calls,
                **kwargs
            )
            
            # Update native context for the next turn
            current_native_context = getattr(response, 'native_context', None)
            last_tool_calls = None # Reset after passing

            # If no step returned, we're done (or there was an error)
            if not response or not response.step:
                print(f"🏁 [ReasoningEngine] Turn {turn_count}: No more steps returned. Finishing.")
                break
                
            step = response.step
            steps.append(step)

            # 2. Check for tool calls (Intents)
            tool_calls = step.tool_calls
            if not tool_calls:
                print(f"🏁 [ReasoningEngine] Turn {turn_count}: No tool calls requested. Finishing.")
                # No more tools to call, reasoning loop finished
                break

            print(f"🛠️ [ReasoningEngine] Turn {turn_count}: Model requested {len(tool_calls)} tool calls: {[tc.name for tc in tool_calls]}")

            # 3. Execute tools
            if not tool_functions:
                logger.warning(f"[ReasoningEngine] Model requested tools { [tc.name for tc in tool_calls] } but no functions provided.")
                # We can't proceed with execution, so break
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
                                    
                        # Format result as JSON string if it's a dict/list
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

            # Feed back the updated steps so far to history for the next turn
            current_turn_msg = Message(
                role=MessageRole.ASSISTANT,
                content=step.content or "Executing tools...",
                sub_messages=list(steps)
            )
            history = list(messages) + [current_turn_msg]
            
            # Store results to be passed natively in the next turn
            last_tool_calls = tool_calls

        # Consolidated Result
        final_content = steps[-1].content if steps else ""
        
        return Message(
            role=MessageRole.ASSISTANT,
            content=final_content,
            sub_messages=steps,
            meta_info={
                "model": model_name,
                "usage": {"total_turns": turn_count}
            }
        )

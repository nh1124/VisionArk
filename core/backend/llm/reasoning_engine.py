"""
Reasoning Engine
Orchestrates multi-turn LLM execution, tool calling, and history management.
Decouples execution logic from LLM connectivity.
"""
import asyncio
import os
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

    def _load_prompt_component(self, name: str) -> str:
        """Helper to load a prompt component from the assets directory."""
        from utils.paths import get_prompts_dir
        prompts_dir = get_prompts_dir()
        path = prompts_dir / "components" / f"{name}.md"

        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Error loading prompt component {name}: {e}")
        return ""

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
                print(f"[ReasoningEngine] Model requested tools { [tc.name for tc in tool_calls] } but no functions provided.")
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
                                    
                        # Execute tool
                        result = await func(**full_kwargs)

                        tc.result = result.content
                        tc.is_success = result.is_success
                        
                        # Standardized attachments (Provider-Agnostic)
                        if result.attachments:
                            for att in result.attachments:
                                tc.attachments.append({
                                    "type": att.type,
                                    "value": att.value,
                                    "mime_type": att.mime_type,
                                    "metadata": att.metadata
                                })
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
        
        # If we had multiple turns or tool calls, run one final summarization to get a clean result
        if len(steps) > 1 or any(s.tool_calls for s in steps):
            if status_callback:
                await status_callback("Summarizing results...", "processing")
            
            print("📝 [ReasoningEngine] Performing summarization turn...")
            
            # Load custom instructions for formatting and identity
            formatting_instr = self._load_prompt_component("formatting")
            identity_instr = self._load_prompt_component("identity")
            
            summary_prompt = identity_instr + "\n\n" + formatting_instr + "\n\n" + (
                "Based on the actions taken and results obtained in the 'Thinking Process' above, "
                "please provide a helpful and natural final response to the user's original request. "
                "Maintain your persona as a proactive assistant, explain what was accomplished, "
                "and suggest any relevant next steps. Respond in the same language as the user."
            )

            # Create a virtual assistant message representing the context so far
            context_msg = Message(
                role=MessageRole.ASSISTANT,
                content="Reasoning complete.",
                sub_messages=steps
            )
            
            # Send the summary prompt to the provider
            # We provide the last user message for context + the full reasoning trace (context_msg)
            # This prevents the model from summarizing the entire conversation history.
            last_user_msg = next((m for m in reversed(messages) if m.role == MessageRole.USER), messages[-1])
            
            summary_response = await self.provider.complete_async(
                messages=[last_user_msg, context_msg, Message(role=MessageRole.USER, content=summary_prompt)],
                system_instruction=system_instruction,
                temperature=0.3,
                **kwargs
            )

            if summary_response and summary_response.step and summary_response.step.content:
                final_content = summary_response.step.content
                print("✅ [ReasoningEngine] Summarization successful.")

        return Message(
            role=MessageRole.ASSISTANT,
            content=final_content,
            sub_messages=steps,
            meta_info={
                "model": model_name,
                "usage": {"total_turns": turn_count}
            }
        )

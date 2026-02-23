"""Execute individual graph steps (role/skill/approval/delegation/responder)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..errors import (
    RegistryKeyError,
    SkillExecutionError,
    ToolExecutionError,
    ToolNotAllowedError,
)
from ..models.common import (
    ApprovalPolicy,
    ApprovalSourceType,
    EventSource,
    EventType,
    MessageRole,
    SubMessageKind,
)
from ..models.execution import (
    ExecutionContext,
    OrchestrationEvent,
    ToolResult,
)
from ..models.graph_spec import GraphStep
from ..models.message import Message, SubMessage, ToolCallRef

if TYPE_CHECKING:
    from ..interfaces.store import Store
    from ..orchestration.approval_manager import ApprovalManager
    from ..orchestration.delegation_manager import DelegationManager
    from ..registry.model_registry import ModelRegistry
    from ..registry.role_registry import RoleRegistry
    from ..registry.skill_registry import SkillRegistry
    from ..registry.tool_registry import ToolRegistry
    from ..models.agent import AgentDef
    from ..models.run import RunRecord
    from ..interfaces.llm_engine import LLMEngine

logger = logging.getLogger(__name__)


class StepExecutor:
    """Executes individual steps within the orchestration graph."""

    def __init__(
        self,
        store: Store,
        tool_registry: ToolRegistry,
        skill_registry: SkillRegistry,
        role_registry: RoleRegistry,
        model_registry: ModelRegistry,
        approval_manager: ApprovalManager,
        delegation_manager: DelegationManager,
        engine_runtime: LLMEngine | None = None,
        delegate_fn: Any | None = None,
    ) -> None:
        self._store = store
        self._tools = tool_registry
        self._skills = skill_registry
        self._roles = role_registry
        self._models = model_registry
        self._approval_mgr = approval_manager
        self._delegation_mgr = delegation_manager
        self._engine = engine_runtime
        self._delegate_fn = delegate_fn

    async def execute_step(
        self,
        step: GraphStep,
        run: RunRecord,
        agent_def: AgentDef,
    ) -> list[OrchestrationEvent]:
        """Execute a graph step and return resulting events."""
        ctx = ExecutionContext(
            run_id=run.run_id,
            agent_def=agent_def,
            run_context=run.context,
            store=self._store,
            metadata=run.metadata,
        )

        if step.type == "role":
            return await self._execute_role_step(step, run, agent_def, ctx)
        elif step.type == "skill":
            return await self._execute_skill_step(step, run, agent_def, ctx)
        elif step.type == "approval":
            return await self._execute_approval_step(step, run)
        elif step.type == "delegation":
            return await self._execute_delegation_step(step, run)
        elif step.type == "responder":
            return await self._execute_responder_step(step, run, agent_def, ctx)
        else:
            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.SYSTEM,
                detail=f"Unknown step type: {step.type}",
            )
            await self._store.append_event(event)
            return [event]

    async def _execute_role_step(
        self,
        step: GraphStep,
        run: RunRecord,
        agent_def: AgentDef,
        ctx: ExecutionContext,
    ) -> list[OrchestrationEvent]:
        """Execute a role step: build prompt, delegate to engine runtime.

        The multi-turn inference loop (LLM call → tool dispatch → repeat)
        is fully owned by the ``LLMEngine``.
        """
        events: list[OrchestrationEvent] = []

        # ── Resolve role ─────────────────────────────────────────
        role_name = step.role
        if not role_name:
            role_name = agent_def.role_bindings.get(step.id)
        if not role_name:
            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=f"No role specified for step '{step.id}'",
            )
            await self._store.append_event(event)
            return [event]

        try:
            role_impl = self._roles.get(role_name)
        except RegistryKeyError:
            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=f"Role '{role_name}' not found in registry",
            )
            await self._store.append_event(event)
            return [event]

        # Build prompt and gather tools (shared by both paths)
        # INJECTION: Filter skill text matching the step's allowed skills
        active_skills_text = ""
        skill_defs = ctx.metadata.get("skill_definitions", {})
        if step.skills and skill_defs:
            # Gather text for each allowed skill
            texts = []
            for skill_name in step.skills:
                if skill_name in skill_defs:
                    texts.append(skill_defs[skill_name])
            active_skills_text = "\n\n".join(texts)
        
        # Determine effective skills text: active subset OR global fallback
        # We store it in metadata so ProjectRole can use it.
        # PlannerRole will likely ignore this and use the global 'skills_text' 
        # (which engine_setup.py populates) if it wants the full list.
        if active_skills_text:
             ctx.metadata["active_skills_text"] = active_skills_text
             logger.debug(
                 "step '%s': active_skills_text set (%d chars, skills=%s)",
                 step.id, len(active_skills_text), step.skills,
             )

        system_prompt = role_impl.build_prompt(ctx)
        tool_defs = self._gather_tool_definitions(agent_def, step_skills=step.skills)

        # ── Engine runtime path (preferred) ──────────────────────
        return await self._execute_role_step_via_engine(
            step, run, agent_def, ctx,
            role_impl=role_impl,
            system_prompt=system_prompt,
            tool_defs=tool_defs,
        )

    async def _execute_role_step_via_engine(
        self,
        step: GraphStep,
        run: RunRecord,
        agent_def: AgentDef,
        ctx: ExecutionContext,
        *,
        role_impl: Any,
        system_prompt: str,
        tool_defs: list[dict[str, Any]],
    ) -> list[OrchestrationEvent]:
        """Role step execution via engine_runtime (multi-turn)."""
        from ..models.engine_io import EngineRunInput, RunOptions

        events: list[OrchestrationEvent] = []

        # Determine limits from step or agent defaults
        max_turns = step.limits.max_turns or agent_def.limits.max_turns
        max_tool_calls = step.limits.max_tool_calls or 50
        max_output_tokens = step.limits.max_output_tokens

        engine_input = EngineRunInput(
            run_id=run.run_id,
            message=run.history[-1] if run.history else run.input_message,
            history=list(run.history),
            system_prompt=system_prompt,
            tool_defs=tool_defs,
            metadata={
                **run.metadata,
                "agent_def": agent_def,
                "run_context": run.context,
                "store": self._store,
            },
        )
        options = RunOptions(
            max_turns=max_turns,
            max_tool_calls=max_tool_calls,
            max_output_tokens=max_output_tokens,
        )

        logger.debug(
            "role_step '%s': delegating to engine_runtime "
            "(max_turns=%d, max_tool_calls=%d, tool_defs=%d, max_output_tokens=%s)",
            step.id, max_turns, max_tool_calls, len(tool_defs),
            max_output_tokens,
        )
        engine_result = await self._engine.run(engine_input, options)

        # ── Map engine result back to orchestration2 structures ──
        # Replace run history with the engine's output history
        run.history = engine_result.history

        # Post-process with role
        output_content = ""
        if engine_result.output_message:
            output_content = engine_result.output_message.content
        role_result = role_impl.post_process(output_content, ctx)

        if engine_result.status == "completed":
            run.output_message = engine_result.output_message

            event = OrchestrationEvent(
                type=EventType.DONE,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=output_content[:200] if output_content else "completed",
            )
            await self._store.append_event(event)
            events.append(event)
        else:
            # Engine returned failed/cancelled
            detail = engine_result.error or "Engine run did not complete"
            # If there is partial output, still capture it
            if engine_result.output_message:
                run.output_message = engine_result.output_message

            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=detail,
            )
            await self._store.append_event(event)
            events.append(event)

        run.context.turn_index += 1
        return events

    async def _handle_tool_call(
        self,
        tool_call: dict[str, Any],
        step: GraphStep,
        run: RunRecord,
        agent_def: AgentDef,
        ctx: ExecutionContext,
    ) -> list[OrchestrationEvent]:
        """Handle a single tool call from the LLM."""
        events: list[OrchestrationEvent] = []
        tool_name = tool_call.get("name", "")
        call_id = tool_call.get("call_id", tool_call.get("id", ""))
        logger.debug("tool_call: tool=%s, call_id=%s", tool_name, call_id)

        # Emit tool_call event
        tc_event = OrchestrationEvent(
            type=EventType.TOOL_CALL,
            run_id=run.run_id,
            step_id=step.id,
            source=EventSource.ROLE,
            detail=tool_name,
        )
        await self._store.append_event(tc_event)
        events.append(tc_event)

        # Skill-tool constraint: check if tool is allowed by active skill
        active_skill = run.context.active_skill
        if active_skill:
            try:
                skill_def = self._skills.get_def(active_skill)
                if skill_def.tools and tool_name not in skill_def.tools:
                    raise ToolNotAllowedError(tool_name, active_skill)
            except RegistryKeyError:
                pass  # Skill not in registry, skip constraint

        # Check if tool exists
        try:
            tool_def, tool_impl = self._tools.get(tool_name)
        except RegistryKeyError:
            error_event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=f"Tool '{tool_name}' not found",
            )
            await self._store.append_event(error_event)
            events.append(error_event)
            return events

        # Check approval policy
        needs_approval = (
            tool_def.request_approval
            or step.policy.approval == ApprovalPolicy.REQUIRED
        )
        if step.policy.approval == ApprovalPolicy.NEVER:
            needs_approval = False

        if needs_approval:
            approval_req = await self._approval_mgr.create_request(
                run_id=run.run_id,
                step_id=step.id,
                source_type=ApprovalSourceType.TOOL,
                source_name=tool_name,
                reason=f"Tool '{tool_name}' requires approval",
            )
            approval_event = OrchestrationEvent(
                type=EventType.NEEDS_APPROVAL,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.APPROVAL,
                detail=f"Approval required for tool '{tool_name}'",
            )
            await self._store.append_event(approval_event)
            events.append(approval_event)
            return events

        # Execute tool
        call_ref = ToolCallRef(
            tool_name=tool_name,
            call_id=call_id,
            arguments=tool_call.get("arguments", {}),
        )
        try:
            result = await tool_impl.invoke(call_ref, ctx)
            logger.debug("tool '%s' result: error=%s", tool_name, result.error)

            # Add tool result to history as a submessage
            sub = SubMessage(
                kind=SubMessageKind.TOOL_RESULT,
                content=result.output,
                tool_call=call_ref,
            )
            tool_msg = Message(
                role=MessageRole.TOOL,
                content=result.output,
                submessages=[sub],
            )
            run.history.append(tool_msg)

            result_event = OrchestrationEvent(
                type=EventType.TOOL_RESULT,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=f"{tool_name}: {result.output[:200]}",
            )
            await self._store.append_event(result_event)
            events.append(result_event)

        except ToolNotAllowedError:
            raise
        except Exception as exc:
            error_event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=f"Tool execution error: {exc}",
            )
            await self._store.append_event(error_event)
            events.append(error_event)
            raise ToolExecutionError(str(exc)) from exc

        run.context.tool_call_count += 1
        return events

    async def _execute_skill_step(
        self,
        step: GraphStep,
        run: RunRecord,
        agent_def: AgentDef,
        ctx: ExecutionContext,
    ) -> list[OrchestrationEvent]:
        """Execute a skill step."""
        events: list[OrchestrationEvent] = []
        skill_name = step.skill
        if not skill_name:
            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.SKILL,
                detail=f"No skill specified for step '{step.id}'",
            )
            await self._store.append_event(event)
            return [event]

        # Set active skill in context
        run.context.active_skill = skill_name
        run.context.active_step_id = step.id

        # Emit skill_selected event
        sel_event = OrchestrationEvent(
            type=EventType.SKILL_SELECTED,
            run_id=run.run_id,
            step_id=step.id,
            source=EventSource.SKILL,
            detail=skill_name,
        )
        await self._store.append_event(sel_event)
        events.append(sel_event)

        try:
            skill_def, skill_impl = self._skills.get(skill_name)

            # Check approval
            if skill_def.request_approval or step.policy.approval == ApprovalPolicy.REQUIRED:
                if step.policy.approval != ApprovalPolicy.NEVER:
                    approval_req = await self._approval_mgr.create_request(
                        run_id=run.run_id,
                        step_id=step.id,
                        source_type=ApprovalSourceType.SKILL,
                        source_name=skill_name,
                        reason=f"Skill '{skill_name}' requires approval",
                    )
                    approval_event = OrchestrationEvent(
                        type=EventType.NEEDS_APPROVAL,
                        run_id=run.run_id,
                        step_id=step.id,
                        source=EventSource.APPROVAL,
                        detail=f"Approval required for skill '{skill_name}'",
                    )
                    await self._store.append_event(approval_event)
                    events.append(approval_event)
                    return events

            result = await skill_impl.run(run.input_message, ctx)

            # Add skill output to history
            for msg in result.messages:
                run.history.append(msg)

            result_event = OrchestrationEvent(
                type=EventType.TOOL_RESULT,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.SKILL,
                detail=f"{skill_name}: {result.output[:200]}",
            )
            await self._store.append_event(result_event)
            events.append(result_event)

        except ToolNotAllowedError:
            raise
        except RegistryKeyError:
            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.SKILL,
                detail=f"Skill '{skill_name}' not found in registry",
            )
            await self._store.append_event(event)
            events.append(event)
        except Exception as exc:
            error_event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.SKILL,
                detail=f"Skill execution error: {exc}",
            )
            await self._store.append_event(error_event)
            events.append(error_event)
            raise SkillExecutionError(str(exc)) from exc
        finally:
            # Clear active skill
            run.context.active_skill = None

        return events

    async def _execute_approval_step(
        self,
        step: GraphStep,
        run: RunRecord,
    ) -> list[OrchestrationEvent]:
        """Execute an approval gate step - returns latest approval events."""
        # The approval step is a waiting point. Check recent events for
        # APPROVED or DENIED events that the approval_manager resolved.
        events = await self._store.get_events(run.run_id)
        recent = [
            e
            for e in events
            if e.type in (EventType.APPROVED, EventType.DENIED)
        ]
        if recent:
            return [recent[-1]]

        # No resolution yet - create a generic approval request
        approval_req = await self._approval_mgr.create_request(
            run_id=run.run_id,
            step_id=step.id,
            source_type=ApprovalSourceType.TOOL,
            source_name="approval_gate",
            reason="Approval gate reached",
        )
        event = OrchestrationEvent(
            type=EventType.NEEDS_APPROVAL,
            run_id=run.run_id,
            step_id=step.id,
            source=EventSource.APPROVAL,
            detail="Waiting for approval",
        )
        await self._store.append_event(event)
        return [event]

    async def _execute_delegation_step(
        self,
        step: GraphStep,
        run: RunRecord,
    ) -> list[OrchestrationEvent]:
        """Execute a delegation step.

        If step.delegate_to is set and _delegate_fn is available:
          → Initiate child run synchronously using last assistant message as task.
        Otherwise:
          → Legacy behavior: check for existing delegation events.
        """
        # ── Graph-native delegation (Phase B) ─────────────────────────
        if step.delegate_to and self._delegate_fn:
            # Extract task from last LLM output, or fallback to input
            last_msgs = [m for m in run.history if m.role == MessageRole.ASSISTANT]
            task = (
                last_msgs[-1].content
                if last_msgs
                else (run.input_message.content if run.input_message else "")
            )

            event_type: EventType
            detail: str
            try:
                result = await self._delegate_fn(
                    run.run_id,
                    step.delegate_to,
                    task,
                    timeout_sec=step.limits.max_turns,
                )

                # Inject child result into parent history
                if result.output_message:
                    child_msg = Message(
                        role=MessageRole.ASSISTANT,
                        content=(
                            f"[Result from sub-agent '{step.delegate_to}']\n"
                            f"{result.output_message.content}"
                        ),
                    )
                    run.history.append(child_msg)
                    run.metadata["last_delegation_result"] = result.model_dump()

                if result.status == "completed":
                    event_type = EventType.DELEGATION_DONE
                    detail = f"Delegation to '{step.delegate_to}' completed"
                else:
                    event_type = EventType.DELEGATION_FAILED
                    detail = (
                        f"Delegation to '{step.delegate_to}' failed: "
                        f"{result.error or 'Unknown error'}"
                    )

            except Exception as exc:
                event_type = EventType.DELEGATION_FAILED
                detail = f"Delegation error: {exc}"

            event = OrchestrationEvent(
                type=event_type,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.DELEGATION,
                detail=detail,
            )
            await self._store.append_event(event)
            return [event]

        # ── Legacy behavior: check existing events ─────────────────────
        events = await self._store.get_events(run.run_id)
        recent = [
            e
            for e in events
            if e.type in (EventType.DELEGATION_DONE, EventType.DELEGATION_FAILED)
        ]
        if recent:
            return [recent[-1]]

        # Delegation is initiated by the orchestrator when it routes here
        event = OrchestrationEvent(
            type=EventType.DELEGATE_TASK,
            run_id=run.run_id,
            step_id=step.id,
            source=EventSource.DELEGATION,
            detail="Delegation step reached",
        )
        await self._store.append_event(event)
        return [event]

    async def _execute_responder_step(
        self,
        step: GraphStep,
        run: RunRecord,
        agent_def: AgentDef,
        ctx: ExecutionContext,
    ) -> list[OrchestrationEvent]:
        """Execute a responder (terminal) step.

        If an output_message was already captured by a prior role step,
        use it directly instead of making a redundant LLM call.
        """
        # Use output already captured by a prior step if available
        if run.output_message and run.output_message.content:
            output_content = run.output_message.content
        else:
            # Fallback: extract from last assistant message in history
            last_assistant = [
                m for m in run.history if m.role == MessageRole.ASSISTANT
            ]
            if last_assistant:
                output_content = last_assistant[-1].content
            else:
                output_content = "Run completed."

        run.output_message = Message(
            role=MessageRole.ASSISTANT,
            content=output_content,
        )

        event = OrchestrationEvent(
            type=EventType.DONE,
            run_id=run.run_id,
            step_id=step.id,
            source=EventSource.SYSTEM,
            detail=output_content[:200],
        )
        await self._store.append_event(event)
        return [event]

    def _gather_tool_definitions(
        self,
        agent_def: AgentDef,
        step_skills: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Gather tool definitions available to the agent for a given step.

        Resolution order:
        1. If *step_skills* is provided and non-empty, use those skill groups.
        2. Else fall back to *agent_def.skills*.
        3. Else expose ALL registered tools (backward compatibility).
        """
        active_skills = step_skills if step_skills else agent_def.skills

        tool_defs: list[dict[str, Any]] = []
        seen: set[str] = set()

        if active_skills:
            for skill_name in active_skills:
                try:
                    skill_def = self._skills.get_def(skill_name)
                    for tool_name in skill_def.tools:
                        if tool_name not in seen:
                            seen.add(tool_name)
                            try:
                                td = self._tools.get_def(tool_name)
                                tool_defs.append(td.model_dump())
                            except RegistryKeyError:
                                logger.warning(
                                    "Tool '%s' referenced by skill '%s' not found",
                                    tool_name,
                                    skill_name,
                                )
                except RegistryKeyError:
                    logger.warning(
                        "Skill '%s' referenced by agent not found", skill_name
                    )
        else:
            # No skills — expose all registered tools
            for td in self._tools.list():
                tool_defs.append(td.model_dump())

        return tool_defs

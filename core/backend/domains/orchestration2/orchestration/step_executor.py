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
    ) -> None:
        self._store = store
        self._tools = tool_registry
        self._skills = skill_registry
        self._roles = role_registry
        self._models = model_registry
        self._approval_mgr = approval_manager
        self._delegation_mgr = delegation_manager

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
        """Execute a role step: build prompt, call LLM, process tool calls."""
        events: list[OrchestrationEvent] = []

        role_name = step.role
        if not role_name:
            # Check agent role_bindings
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

        # Build prompt
        system_prompt = role_impl.build_prompt(ctx)

        # Gather available tools from agent's skills
        tool_defs = self._gather_tool_definitions(agent_def)

        # Call LLM
        model_name = agent_def.default_model
        try:
            model_config = self._models.get(model_name)
        except RegistryKeyError:
            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=f"Model '{model_name}' not found in registry",
            )
            await self._store.append_event(event)
            return [event]

        # Get LLM provider (stored in model config extra as provider_impl)
        provider = model_config.extra.get("provider_impl")
        if provider is None:
            event = OrchestrationEvent(
                type=EventType.ERROR,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=f"No LLM provider implementation for model '{model_name}'",
            )
            await self._store.append_event(event)
            return [event]

        messages = list(run.history) + [run.input_message]
        llm_response = await provider.complete(
            messages=messages,
            system=system_prompt,
            tools=tool_defs,
            model=model_config.model_id,
        )

        # Post-process with role
        role_result = role_impl.post_process(llm_response.content, ctx)

        # Handle tool calls from LLM response
        if llm_response.tool_calls:
            for tc in llm_response.tool_calls:
                tool_events = await self._handle_tool_call(
                    tc, step, run, agent_def, ctx
                )
                events.extend(tool_events)
        elif role_result.done:
            # Role signals completion
            event = OrchestrationEvent(
                type=EventType.DONE,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=role_result.output,
            )
            await self._store.append_event(event)
            events.append(event)

            # Store output as assistant message
            run.output_message = Message(
                role=MessageRole.ASSISTANT,
                content=role_result.output,
            )
        else:
            # LLM produced text but no tool calls and not done - continue
            # Add assistant message to history
            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content=llm_response.content,
            )
            run.history.append(assistant_msg)

            event = OrchestrationEvent(
                type=EventType.DONE,
                run_id=run.run_id,
                step_id=step.id,
                source=EventSource.ROLE,
                detail=llm_response.content,
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
        call_id = tool_call.get("id", "")

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
        call_ref = ToolCallRef(tool_name=tool_name, call_id=call_id)
        try:
            result = await tool_impl.invoke(call_ref, ctx)

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
        """Execute a delegation step - check for pending delegations."""
        # Check if there are pending delegation results
        events = await self._store.get_events(run.run_id)
        recent = [
            e
            for e in events
            if e.type
            in (EventType.DELEGATION_DONE, EventType.DELEGATION_FAILED)
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
        """Execute a responder (terminal) step."""
        role_name = step.role
        if not role_name:
            role_name = agent_def.role_bindings.get(step.id)

        output_content = ""
        if role_name:
            try:
                role_impl = self._roles.get(role_name)
                system_prompt = role_impl.build_prompt(ctx)

                model_name = agent_def.default_model
                model_config = self._models.get(model_name)
                provider = model_config.extra.get("provider_impl")

                if provider:
                    messages = list(run.history) + [run.input_message]
                    llm_response = await provider.complete(
                        messages=messages,
                        system=system_prompt,
                        model=model_config.model_id,
                    )
                    role_result = role_impl.post_process(
                        llm_response.content, ctx
                    )
                    output_content = role_result.output
                else:
                    output_content = "No LLM provider available for response."
            except RegistryKeyError:
                output_content = "Responder role not found."
        else:
            # No role, use last assistant message or input
            if run.history:
                last_assistant = [
                    m for m in run.history if m.role == MessageRole.ASSISTANT
                ]
                if last_assistant:
                    output_content = last_assistant[-1].content
            if not output_content:
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
        self, agent_def: AgentDef
    ) -> list[dict[str, Any]]:
        """Gather tool definitions from all skills assigned to the agent."""
        tool_defs: list[dict[str, Any]] = []
        seen: set[str] = set()

        for skill_name in agent_def.skills:
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

        return tool_defs

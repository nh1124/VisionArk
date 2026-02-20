"""Main orchestration run loop: step execution, event routing, state transitions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ..errors import (
    GraphValidationError,
    LimitsExceededError,
    RegistryKeyError,
    RunNotFoundError,
    ToolNotAllowedError,
)
from ..models.common import EventType, RunStatus
from ..models.execution import OrchestrationEvent, RunResponse
from ..models.graph_spec import GraphSpec
from ..models.message import Message
from ..models.run import RunRecord
from .graph_compiler import evaluate_when

if TYPE_CHECKING:
    from ..interfaces.store import Store
    from ..models.agent import AgentDef
    from .step_executor import StepExecutor

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestration engine that drives run execution through a graph."""

    def __init__(self, store: Store, step_executor: StepExecutor) -> None:
        self._store = store
        self._step_executor = step_executor

    async def run(
        self,
        agent_def: AgentDef,
        graph: GraphSpec,
        message: Message,
        history: list[Message] | None = None,
        parent_run_id: str | None = None,
        metadata: dict | None = None,
        run_id: str | None = None,
    ) -> RunResponse:
        """Execute a full orchestration run and return the response."""
        # Create RunRecord — append input message to history so the
        # conversation is always in correct order (user, model, tool, …).
        combined_history = list(history) if history else []
        combined_history.append(message)
        record_kwargs: dict = dict(
            status=RunStatus.RUNNING,
            agent_name=agent_def.name,
            graph_name=graph.graph_name,
            input_message=message,
            history=combined_history,
            current_step_id=graph.start,
            metadata=metadata or {},
        )
        if run_id is not None:
            record_kwargs["run_id"] = run_id
        run = RunRecord(**record_kwargs)
        await self._store.save_run(run)

        # Build step lookup and run the main loop
        step_map = {step.id: step for step in graph.steps}
        return await self._run_loop(run, agent_def, step_map)

    async def resume(
        self,
        run_id: str,
        agent_def: AgentDef,
        graph: GraphSpec,
    ) -> RunResponse:
        """Resume a suspended run (after approval/delegation resolution)."""
        run = await self._store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        if run.status not in (
            RunStatus.WAITING_APPROVAL,
            RunStatus.WAITING_DELEGATION,
            RunStatus.RUNNING,
        ):
            return self._build_response(run)

        # Set status back to RUNNING so the loop can proceed
        run.status = RunStatus.RUNNING
        await self._store.save_run(run)

        # Build step lookup and re-enter the loop from current_step_id
        step_map = {step.id: step for step in graph.steps}
        return await self._run_loop(run, agent_def, step_map)

    async def _run_loop(
        self,
        run: RunRecord,
        agent_def: AgentDef,
        step_map: dict[str, object],
    ) -> RunResponse:
        """Shared step-execution loop used by both run() and resume()."""
        current_step_id = run.current_step_id or next(iter(step_map))
        max_iterations = agent_def.limits.max_turns * 3  # safety limit

        try:
            for _ in range(max_iterations):
                step = step_map.get(current_step_id)
                if step is None:
                    run.status = RunStatus.FAILED
                    run.error = f"Step '{current_step_id}' not found in graph"
                    break

                run.current_step_id = current_step_id
                run.context.active_step_id = current_step_id
                await self._store.save_run(run)

                # Check turn/tool limits — skip for role steps when engine
                # runtime handles them (limits are enforced inside the engine).
                engine_handles_limits = (
                    step.type == "role"
                    and self._step_executor._engine is not None
                )
                if not engine_handles_limits:
                    step_max_turns = step.limits.max_turns or agent_def.limits.max_turns
                    if run.context.turn_index >= step_max_turns:
                        raise LimitsExceededError(
                            f"Turn limit ({step_max_turns}) exceeded at step '{step.id}'"
                        )

                    if step.limits.max_tool_calls is not None:
                        if run.context.tool_call_count >= step.limits.max_tool_calls:
                            raise LimitsExceededError(
                                f"Tool call limit ({step.limits.max_tool_calls}) "
                                f"exceeded at step '{step.id}'"
                            )

                # Execute step
                logger.debug(
                    "Executing step '%s' (type=%s, terminal=%s)",
                    current_step_id, step.type, step.terminal,
                )
                events = await self._step_executor.execute_step(
                    step, run, agent_def
                )

                # Refresh status/pending IDs from DB (may have been changed by
                # approval/delegation managers) but preserve fields that the
                # step executor modified in-memory and haven't been saved yet.
                refreshed_run = await self._store.get_run(run.run_id)
                if refreshed_run:
                    refreshed_run.input_message = run.input_message
                    refreshed_run.history = run.history
                    refreshed_run.output_message = run.output_message
                    refreshed_run.metadata = run.metadata
                    refreshed_run.context = run.context
                    run = refreshed_run

                if run.status in (
                    RunStatus.WAITING_APPROVAL,
                    RunStatus.WAITING_DELEGATION,
                ):
                    return self._build_response(run)

                # Check for external cancellation
                if run.status == RunStatus.CANCELLED:
                    logger.info("Run %s was cancelled externally", run.run_id)
                    run.error = run.error or "Cancelled by user"
                    break

                # If terminal step, complete
                if step.terminal:
                    logger.debug("Step '%s' is terminal — completing run", current_step_id)
                    run.status = RunStatus.COMPLETED
                    break

                # Route to next step based on events
                next_step_id = self._resolve_next_step(step, events)
                logger.debug("Transition '%s' -> '%s'", current_step_id, next_step_id)
                if next_step_id is None:
                    run.status = RunStatus.COMPLETED
                    break

                # Reset per-step counters when moving to a different step
                if next_step_id != current_step_id:
                    run.context.turn_index = 0
                    run.context.tool_call_count = 0

                current_step_id = next_step_id

            else:
                # Exhausted iteration limit
                run.status = RunStatus.FAILED
                run.error = "Maximum iteration limit reached"

        except (ToolNotAllowedError, LimitsExceededError) as exc:
            run.status = RunStatus.FAILED
            run.error = str(exc)
            logger.error("Run %s failed: %s", run.run_id, exc)
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error = f"Unexpected error: {exc}"
            logger.exception("Run %s failed unexpectedly", run.run_id)

        logger.debug("Run %s finished: status=%s", run.run_id, run.status.value)
        run.updated_at = datetime.utcnow()
        await self._store.save_run(run)
        return self._build_response(run)

    def _resolve_next_step(
        self,
        current_step: object,
        events: list[OrchestrationEvent],
    ) -> str | None:
        """Evaluate transitions and return the next step ID."""
        from ..models.graph_spec import GraphStep

        step: GraphStep = current_step  # type: ignore[assignment]
        if not step.on:
            return None

        # Use the last event for transition evaluation
        last_event = events[-1] if events else None
        if last_event is None:
            return None

        default_next: str | None = None

        for transition in step.on:
            if transition.when.strip() == "default":
                default_next = transition.next
                continue
            if evaluate_when(transition.when, last_event):
                return transition.next

        return default_next

    def _build_response(self, run: RunRecord) -> RunResponse:
        """Build a RunResponse from the current run state."""
        return RunResponse(
            run_id=run.run_id,
            completed=run.status == RunStatus.COMPLETED,
            message=run.output_message,
            history=run.history,
            error=run.error,
            approval_requests=[],  # populated by caller if needed
            delegation_requests=[],
        )


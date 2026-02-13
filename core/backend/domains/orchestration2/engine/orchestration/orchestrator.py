"""Main orchestration run loop: step execution, event routing, state transitions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..errors import (
    GraphValidationError,
    LimitsExceededError,
    RegistryKeyError,
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
    ) -> RunResponse:
        """Execute a full orchestration run and return the response."""
        # Create RunRecord
        run = RunRecord(
            status=RunStatus.RUNNING,
            agent_name=agent_def.name,
            graph_name=graph.graph_name,
            input_message=message,
            history=list(history) if history else [],
            current_step_id=graph.start,
        )
        await self._store.save_run(run)

        # Build step lookup
        step_map = {step.id: step for step in graph.steps}

        current_step_id = graph.start
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

                # Check turn limits
                step_max_turns = step.limits.max_turns or agent_def.limits.max_turns
                if run.context.turn_index >= step_max_turns:
                    raise LimitsExceededError(
                        f"Turn limit ({step_max_turns}) exceeded at step '{step.id}'"
                    )

                # Check tool call limits
                if step.limits.max_tool_calls is not None:
                    if run.context.tool_call_count >= step.limits.max_tool_calls:
                        raise LimitsExceededError(
                            f"Tool call limit ({step.limits.max_tool_calls}) "
                            f"exceeded at step '{step.id}'"
                        )

                # Execute step
                events = await self._step_executor.execute_step(
                    step, run, agent_def
                )

                # Check if run was suspended (approval/delegation)
                refreshed_run = await self._store.get_run(run.run_id)
                if refreshed_run:
                    run = refreshed_run

                if run.status in (
                    RunStatus.WAITING_APPROVAL,
                    RunStatus.WAITING_DELEGATION,
                ):
                    return self._build_response(run)

                # If terminal step, complete
                if step.terminal:
                    run.status = RunStatus.COMPLETED
                    break

                # Route to next step based on events
                next_step_id = self._resolve_next_step(step, events)
                if next_step_id is None:
                    # No matching transition - run is done
                    run.status = RunStatus.COMPLETED
                    break

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

        run.updated_at = datetime.now(timezone.utc)
        await self._store.save_run(run)
        return self._build_response(run)

    async def resume(self, run_id: str) -> RunResponse:
        """Resume a suspended run (after approval/delegation resolution)."""
        run = await self._store.get_run(run_id)
        if run is None:
            from ..errors import RunNotFoundError

            raise RunNotFoundError(run_id)

        if run.status not in (
            RunStatus.WAITING_APPROVAL,
            RunStatus.WAITING_DELEGATION,
            RunStatus.RUNNING,
        ):
            return self._build_response(run)

        # Get the agent def and graph to continue
        # These need to be provided externally; for now return current state
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
            approval_requests=[],  # populated by caller if needed
            delegation_requests=[],
        )

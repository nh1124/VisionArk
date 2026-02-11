"""Approval manager: create requests, suspend/resume runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..errors import RunNotFoundError
from ..interfaces.store import Store
from ..models.approval import ApprovalDecision, ApprovalRequest, PendingAction
from ..models.common import ApprovalSourceType, EventSource, EventType, RunStatus
from ..models.execution import OrchestrationEvent

logger = logging.getLogger(__name__)


class ApprovalManager:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def create_request(
        self,
        run_id: str,
        step_id: str,
        source_type: ApprovalSourceType,
        source_name: str,
        reason: str,
    ) -> ApprovalRequest:
        """Create an approval request and suspend the run."""
        request = ApprovalRequest(
            run_id=run_id,
            source_type=source_type,
            source_name=source_name,
            reason=reason,
        )

        # Save as PendingAction in store
        action = PendingAction(
            approval_request_id=request.id,
            run_id=run_id,
            step_id=step_id,
            action_type=source_type,
            action_name=source_name,
        )
        await self._store.save_approval(action)

        # Update run status to WAITING_APPROVAL
        run = await self._store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        run.status = RunStatus.WAITING_APPROVAL
        run.pending_approval_ids.append(request.id)
        run.updated_at = datetime.now(timezone.utc)
        await self._store.save_run(run)

        # Emit event
        event = OrchestrationEvent(
            type=EventType.NEEDS_APPROVAL,
            run_id=run_id,
            step_id=step_id,
            source=EventSource.APPROVAL,
            detail=f"{source_type.value}:{source_name} - {reason}",
        )
        await self._store.append_event(event)

        logger.info(
            "Approval request created: %s for run %s", request.id, run_id
        )
        return request

    async def resolve(
        self,
        run_id: str,
        decisions: list[ApprovalDecision],
    ) -> list[OrchestrationEvent]:
        """Resolve approval decisions and return events for each."""
        run = await self._store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(run_id)

        events: list[OrchestrationEvent] = []

        for decision in decisions:
            action = await self._store.get_approval(decision.request_id)
            if action is None:
                logger.warning(
                    "Approval request %s not found, skipping",
                    decision.request_id,
                )
                continue

            event_type = (
                EventType.APPROVED if decision.approved else EventType.DENIED
            )
            detail = decision.comment
            if not decision.approved:
                detail = f"user denied to call the tool {action.action_name}."

            event = OrchestrationEvent(
                type=event_type,
                run_id=run_id,
                step_id=action.step_id,
                source=EventSource.APPROVAL,
                detail=detail,
            )
            await self._store.append_event(event)
            events.append(event)

            # Remove from pending
            if decision.request_id in run.pending_approval_ids:
                run.pending_approval_ids.remove(decision.request_id)

        # If no more pending approvals, set back to RUNNING
        if not run.pending_approval_ids:
            run.status = RunStatus.RUNNING

        run.updated_at = datetime.now(timezone.utc)
        await self._store.save_run(run)

        return events

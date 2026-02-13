"""Delegation manager: create child runs, wait/collect results (Phase 2)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ..errors import DelegationError, RunNotFoundError
from ..models.common import EventSource, EventType, RunStatus
from ..models.delegation import (
    DelegationRequest,
    DelegationResult,
    DelegationResultStatus,
)
from ..models.execution import OrchestrationEvent

if TYPE_CHECKING:
    from ..interfaces.store import Store

logger = logging.getLogger(__name__)


class DelegationManager:
    def __init__(self, store: "Store") -> None:
        self._store = store

    async def delegate(
        self,
        parent_run_id: str,
        child_agent_name: str,
        task: str,
        step_id: str,
        timeout_sec: int | None = None,
    ) -> DelegationRequest:
        """Create a delegation request for a child agent run."""
        parent_run = await self._store.get_run(parent_run_id)
        if parent_run is None:
            raise RunNotFoundError(parent_run_id)

        request = DelegationRequest(
            parent_run_id=parent_run_id,
            child_agent_name=child_agent_name,
            task=task,
            timeout_sec=timeout_sec,
        )
        await self._store.save_delegation(request)

        # Update parent run
        parent_run.status = RunStatus.WAITING_DELEGATION
        parent_run.pending_delegation_ids.append(request.id)
        parent_run.updated_at = datetime.utcnow()
        await self._store.save_run(parent_run)

        # Emit event
        event = OrchestrationEvent(
            type=EventType.DELEGATE_TASK,
            run_id=parent_run_id,
            step_id=step_id,
            source=EventSource.DELEGATION,
            detail=f"Delegating to '{child_agent_name}': {task}",
        )
        await self._store.append_event(event)

        logger.info(
            "Delegation request %s created: parent=%s child_agent=%s",
            request.id,
            parent_run_id,
            child_agent_name,
        )
        return request

    async def complete_delegation(
        self,
        delegation_id: str,
        child_run_id: str,
        status: DelegationResultStatus,
        output_message: object | None = None,
        error: str | None = None,
    ) -> DelegationResult:
        """Record the result of a child delegation."""
        request = await self._store.get_delegation(delegation_id)
        if request is None:
            raise DelegationError(f"Delegation '{delegation_id}' not found")

        result = DelegationResult(
            delegation_id=delegation_id,
            child_run_id=child_run_id,
            status=status,
            output_message=output_message,  # type: ignore[arg-type]
            error=error,
        )
        await self._store.save_delegation_result(result)

        # Update parent run
        parent_run = await self._store.get_run(request.parent_run_id)
        if parent_run is not None:
            if delegation_id in parent_run.pending_delegation_ids:
                parent_run.pending_delegation_ids.remove(delegation_id)
            if not parent_run.pending_delegation_ids:
                parent_run.status = RunStatus.RUNNING
            parent_run.updated_at = datetime.utcnow()
            await self._store.save_run(parent_run)

        # Emit event
        event_type = (
            EventType.DELEGATION_DONE
            if status == DelegationResultStatus.COMPLETED
            else EventType.DELEGATION_FAILED
        )
        event = OrchestrationEvent(
            type=event_type,
            run_id=request.parent_run_id,
            step_id="",
            source=EventSource.DELEGATION,
            detail=f"Delegation {delegation_id} {status.value}: child_run={child_run_id}",
        )
        await self._store.append_event(event)

        return result

    async def wait_result(
        self, delegation_id: str, timeout: float | None = None
    ) -> DelegationResult:
        """Poll for a delegation result with optional timeout."""
        elapsed = 0.0
        poll_interval = 0.5

        while True:
            result = await self._store.get_delegation_result(delegation_id)
            if result is not None:
                return result

            if timeout is not None and elapsed >= timeout:
                # Timeout: create a timeout result
                request = await self._store.get_delegation(delegation_id)
                child_run_id = ""
                if request:
                    child_run_id = f"timeout-{request.id}"
                return DelegationResult(
                    delegation_id=delegation_id,
                    child_run_id=child_run_id,
                    status=DelegationResultStatus.TIMEOUT,
                    error=f"Delegation timed out after {timeout}s",
                )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

"""In-memory implementation of the Store protocol."""

from __future__ import annotations

from ..models.approval import PendingAction
from ..models.delegation import (
    DelegationDeliveryStatus,
    DelegationRequest,
    DelegationResult,
)
from ..models.execution import OrchestrationEvent
from ..models.run import RunRecord


class InMemoryStore:
    """Dict-based store for development and testing."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._approvals: dict[str, PendingAction] = {}
        self._delegations: dict[str, DelegationRequest] = {}
        self._delegation_results: dict[str, DelegationResult] = {}
        self._events: dict[str, list[OrchestrationEvent]] = {}
        self._delivery_cursor: int = 0

    async def save_run(self, record: RunRecord) -> None:
        self._runs[record.run_id] = record

    async def get_run(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    async def save_approval(self, action: PendingAction) -> None:
        self._approvals[action.approval_request_id] = action

    async def get_approval(self, approval_id: str) -> PendingAction | None:
        return self._approvals.get(approval_id)

    async def save_delegation(self, request: DelegationRequest) -> None:
        self._delegations[request.id] = request

    async def get_delegation(
        self, delegation_id: str
    ) -> DelegationRequest | None:
        return self._delegations.get(delegation_id)

    async def find_delegation_by_request_id(
        self, parent_run_id: str, request_id: str
    ) -> DelegationRequest | None:
        for delegation in self._delegations.values():
            if (
                delegation.parent_run_id == parent_run_id
                and delegation.request_id == request_id
            ):
                return delegation
        return None

    async def save_delegation_result(self, result: DelegationResult) -> None:
        cursor = result.delivery_cursor
        if cursor is None:
            self._delivery_cursor += 1
            cursor = self._delivery_cursor
        result.delivery_cursor = cursor
        if result.delivery_status is None:
            result.delivery_status = DelegationDeliveryStatus.DELIVERED
        self._delegation_results[result.delegation_id] = result

    async def get_delegation_result(
        self, delegation_id: str
    ) -> DelegationResult | None:
        return self._delegation_results.get(delegation_id)

    async def list_delegation_results_since(
        self,
        *,
        parent_run_id: str,
        since_cursor: int,
        limit: int,
        include_acknowledged: bool = False,
    ) -> list[DelegationResult]:
        items: list[DelegationResult] = []
        for delegation_id, result in self._delegation_results.items():
            request = self._delegations.get(delegation_id)
            if not request or request.parent_run_id != parent_run_id:
                continue
            cursor = result.delivery_cursor or 0
            if cursor <= since_cursor:
                continue
            if (
                not include_acknowledged
                and result.delivery_status == DelegationDeliveryStatus.ACKNOWLEDGED
            ):
                continue
            items.append(result)

        items.sort(key=lambda item: item.delivery_cursor or 0)
        return items[:limit]

    async def acknowledge_delegation_result(self, delegation_id: str) -> bool:
        result = self._delegation_results.get(delegation_id)
        if result is None:
            return False
        if result.delivery_status == DelegationDeliveryStatus.ACKNOWLEDGED:
            return False
        result.delivery_status = DelegationDeliveryStatus.ACKNOWLEDGED
        return True

    async def append_event(self, event: OrchestrationEvent) -> None:
        if event.run_id not in self._events:
            self._events[event.run_id] = []
        self._events[event.run_id].append(event)

    async def get_events(self, run_id: str) -> list[OrchestrationEvent]:
        return list(self._events.get(run_id, []))

"""Store interface protocol for swappable backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models.approval import PendingAction
from ..models.delegation import DelegationRequest, DelegationResult
from ..models.execution import OrchestrationEvent
from ..models.run import RunRecord


@runtime_checkable
class Store(Protocol):
    async def save_run(self, record: RunRecord) -> None: ...

    async def get_run(self, run_id: str) -> RunRecord | None: ...

    async def save_approval(self, action: PendingAction) -> None: ...

    async def get_approval(self, approval_id: str) -> PendingAction | None: ...

    async def save_delegation(self, request: DelegationRequest) -> None: ...

    async def get_delegation(
        self, delegation_id: str
    ) -> DelegationRequest | None: ...

    async def save_delegation_result(self, result: DelegationResult) -> None: ...

    async def get_delegation_result(
        self, delegation_id: str
    ) -> DelegationResult | None: ...

    async def append_event(self, event: OrchestrationEvent) -> None: ...

    async def get_events(self, run_id: str) -> list[OrchestrationEvent]: ...

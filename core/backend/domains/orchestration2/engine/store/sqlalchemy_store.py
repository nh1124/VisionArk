"""SQLAlchemy implementation of the Store protocol.

Persists orchestration2 data to the database using the OrchestrationRun
and OrchestrationEvent tables defined in shared/database.py.

Approvals and delegations are kept in-memory during a single run since
they are short-lived coordination state (resolved within the same request).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.approval import PendingAction
from ..models.common import EventSource, EventType, RunStatus
from ..models.delegation import DelegationRequest, DelegationResult
from ..models.execution import OrchestrationEvent
from ..models.message import Message
from ..models.run import RunContext, RunRecord

logger = logging.getLogger(__name__)


class SQLAlchemyStore:
    """Store implementation backed by PostgreSQL via SQLAlchemy async session."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session
        # Short-lived coordination state (per-request)
        self._approvals: dict[str, PendingAction] = {}
        self._delegations: dict[str, DelegationRequest] = {}
        self._delegation_results: dict[str, DelegationResult] = {}
        # In-memory event buffer (also persisted to DB)
        self._events: dict[str, list[OrchestrationEvent]] = {}

    # ── RunRecord ─────────────────────────────────────────────────────

    @staticmethod
    def _serializable_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of metadata with non-JSON-serializable values removed."""
        clean: dict[str, Any] = {}
        for key, value in metadata.items():
            try:
                json.dumps(value)
                clean[key] = value
            except (TypeError, ValueError, OverflowError):
                pass
        return clean

    async def save_run(self, record: RunRecord) -> None:
        """Upsert a RunRecord into orchestration_runs."""
        context_data = record.context.model_dump() if record.context else {}
        metadata_data = self._serializable_metadata(record.metadata or {})

        await self._db.execute(
            text("""
                INSERT INTO orchestration_runs
                    (run_id, status, agent_name, graph_name,
                     project_id, user_id, session_id,
                     current_step_id, context_json, metadata_json,
                     error, created_at, updated_at)
                VALUES
                    (:run_id, :status, :agent_name, :graph_name,
                     :project_id, :user_id, :session_id,
                     :current_step_id, :context_json, :metadata_json,
                     :error, :created_at, :updated_at)
                ON CONFLICT (run_id) DO UPDATE SET
                    status = :status,
                    current_step_id = :current_step_id,
                    context_json = :context_json,
                    metadata_json = :metadata_json,
                    error = :error,
                    updated_at = :updated_at
            """),
            {
                "run_id": record.run_id,
                "status": record.status.value,
                "agent_name": record.agent_name,
                "graph_name": record.graph_name,
                "project_id": metadata_data.get("project_id"),
                "user_id": metadata_data.get("user_id"),
                "session_id": metadata_data.get("session_id"),
                "current_step_id": record.current_step_id,
                "context_json": json.dumps(context_data),
                "metadata_json": json.dumps(metadata_data),
                "error": record.error,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            },
        )
        await self._db.flush()

    async def get_run(self, run_id: str) -> RunRecord | None:
        """Load a RunRecord from orchestration_runs."""
        result = await self._db.execute(
            text("SELECT * FROM orchestration_runs WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        row = result.mappings().first()
        if row is None:
            return None

        context_data = row["context_json"] or {}
        if isinstance(context_data, str):
            context_data = json.loads(context_data)

        metadata_data = row["metadata_json"] or {}
        if isinstance(metadata_data, str):
            metadata_data = json.loads(metadata_data)

        return RunRecord(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            agent_name=row["agent_name"],
            graph_name=row["graph_name"],
            current_step_id=row["current_step_id"],
            context=RunContext(**context_data),
            metadata=metadata_data,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Approvals (in-memory, short-lived) ────────────────────────────

    async def save_approval(self, action: PendingAction) -> None:
        self._approvals[action.approval_request_id] = action

    async def get_approval(self, approval_id: str) -> PendingAction | None:
        return self._approvals.get(approval_id)

    # ── Delegations (in-memory, short-lived) ──────────────────────────

    async def save_delegation(self, request: DelegationRequest) -> None:
        self._delegations[request.id] = request

    async def get_delegation(
        self, delegation_id: str
    ) -> DelegationRequest | None:
        return self._delegations.get(delegation_id)

    async def save_delegation_result(self, result: DelegationResult) -> None:
        self._delegation_results[result.delegation_id] = result

    async def get_delegation_result(
        self, delegation_id: str
    ) -> DelegationResult | None:
        return self._delegation_results.get(delegation_id)

    # ── Events ────────────────────────────────────────────────────────

    async def append_event(self, event: OrchestrationEvent) -> None:
        """Persist an event to the DB and buffer it in-memory."""
        # In-memory buffer for fast access during the run
        if event.run_id not in self._events:
            self._events[event.run_id] = []
        self._events[event.run_id].append(event)

        # Persist to DB
        await self._db.execute(
            text("""
                INSERT INTO orchestration_events
                    (id, run_id, step_id, event_type, source, detail, created_at)
                VALUES
                    (:id, :run_id, :step_id, :event_type, :source, :detail, :created_at)
            """),
            {
                "id": event.id,
                "run_id": event.run_id,
                "step_id": event.step_id,
                "event_type": event.type.value,
                "source": event.source.value,
                "detail": event.detail,
                "created_at": event.created_at,
            },
        )
        await self._db.flush()

    async def get_events(self, run_id: str) -> list[OrchestrationEvent]:
        """Return events from in-memory buffer first, fall back to DB."""
        if run_id in self._events:
            return list(self._events[run_id])

        # Fall back to DB for historical queries
        result = await self._db.execute(
            text(
                "SELECT * FROM orchestration_events "
                "WHERE run_id = :run_id ORDER BY created_at"
            ),
            {"run_id": run_id},
        )
        rows = result.mappings().all()
        return [
            OrchestrationEvent(
                id=row["id"],
                type=EventType(row["event_type"]),
                run_id=row["run_id"],
                step_id=row["step_id"] or "",
                source=EventSource(row["source"]),
                detail=row["detail"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

"""SQLAlchemy implementation of the Store protocol.

Persists orchestration2 data to the database using the OrchestrationRun,
OrchestrationPendingAction, OrchestrationDelegation and OrchestrationEvent
tables defined in shared/database.py.

All state (approvals, delegations, run fields) is persisted to DB so that
runs can survive process restarts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text

from ..models.approval import PendingAction
from ..models.common import ApprovalSourceType, EventSource, EventType, RunStatus
from ..models.delegation import (
    DelegationDeliveryStatus,
    DelegationRequest,
    DelegationResult,
    DelegationResultStatus,
)
from ..models.execution import OrchestrationEvent
from ..models.message import Message
from ..models.run import RunContext, RunRecord

logger = logging.getLogger(__name__)


class SQLAlchemyStore:
    """Store implementation backed by PostgreSQL via SQLAlchemy async session.

    Accepts a *session factory* (e.g. ``AsyncSessionLocal``) rather than a
    shared ``AsyncSession``.  Each Store operation opens its own short-lived
    session and commits immediately.

    Rationale: the orchestration engine runs inside an ``asyncio.Task`` created
    by ``AgentEngine._execute_async``.  That Task is different from the caller's
    Task.  SQLAlchemy's asyncpg dialect uses greenlets internally and must not
    be shared across asyncio Task boundaries — doing so corrupts the connection
    state and causes ``InterfaceError: cannot perform operation: another
    operation is in progress`` at session-close time.
    """

    def __init__(self, session_factory) -> None:
        # session_factory: () -> async context manager yielding AsyncSession
        self._factory = session_factory
        # In-memory event buffer (also persisted to DB)
        self._events: dict[str, list[OrchestrationEvent]] = {}

    # ── Serialization helpers ─────────────────────────────────────────

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

    @staticmethod
    def _sanitize_value(value: Any) -> Any:
        """Make a value JSON-safe: fix invalid UTF-8, convert datetimes, etc."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value.encode("utf-8", errors="replace").decode("utf-8")
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, dict):
            return {k: SQLAlchemyStore._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [SQLAlchemyStore._sanitize_value(v) for v in value]
        return value

    @staticmethod
    def _serialize_message(msg: Message | None) -> dict | None:
        if msg is None:
            return None
        return msg.model_dump(mode="json")

    @staticmethod
    def _deserialize_message(data: Any) -> Message | None:
        if data is None:
            return None
        if isinstance(data, str):
            data = json.loads(data)
        return Message(**data)

    @staticmethod
    def _serialize_history(history: list[Message]) -> list[dict]:
        result = []
        for m in history:
            try:
                result.append(m.model_dump(mode="json"))
            except UnicodeDecodeError:
                # Fallback: dump then sanitize any non-UTF-8 byte sequences
                raw = m.model_dump()
                result.append(SQLAlchemyStore._sanitize_value(raw))
        return result

    @staticmethod
    def _deserialize_history(data: Any) -> list[Message]:
        if data is None:
            return []
        if isinstance(data, str):
            data = json.loads(data)
        return [Message(**item) for item in data]

    async def _next_delivery_cursor(self, db) -> int:
        """Allocate a monotonic cursor for delegation result delivery."""
        bind = db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""

        # Preferred path: Postgres sequence for strictly monotonic IDs.
        if dialect == "postgresql":
            try:
                seq_row = await db.execute(
                    text("SELECT nextval('orchestration_delegations_delivery_cursor_seq') AS cursor")
                )
                return int(seq_row.mappings().first()["cursor"])
            except Exception:
                logger.warning("Falling back to MAX(delivery_cursor)+1 allocation")

        # Fallback path for non-Postgres engines.
        max_row = await db.execute(
            text(
                "SELECT COALESCE(MAX(delivery_cursor), 0) + 1 AS cursor "
                "FROM orchestration_delegations"
            )
        )
        return int(max_row.mappings().first()["cursor"])

    # ── RunRecord ─────────────────────────────────────────────────────

    async def save_run(self, record: RunRecord) -> None:
        """Upsert a RunRecord into orchestration_runs."""
        context_data = record.context.model_dump() if record.context else {}
        metadata_data = self._serializable_metadata(record.metadata or {})

        async with self._factory() as db:
            await db.execute(
                text("""
                    INSERT INTO orchestration_runs
                        (run_id, status, agent_name, graph_name,
                         project_id, user_id, session_id,
                         current_step_id, context_json, metadata_json,
                         pending_approval_ids, pending_delegation_ids,
                         history_json, input_message_json, output_message_json,
                         error, created_at, updated_at)
                    VALUES
                        (:run_id, :status, :agent_name, :graph_name,
                         :project_id, :user_id, :session_id,
                         :current_step_id, :context_json, :metadata_json,
                         :pending_approval_ids, :pending_delegation_ids,
                         :history_json, :input_message_json, :output_message_json,
                         :error, :created_at, :updated_at)
                    ON CONFLICT (run_id) DO UPDATE SET
                        status = :status,
                        current_step_id = :current_step_id,
                        context_json = :context_json,
                        metadata_json = :metadata_json,
                        pending_approval_ids = :pending_approval_ids,
                        pending_delegation_ids = :pending_delegation_ids,
                        history_json = :history_json,
                        input_message_json = :input_message_json,
                        output_message_json = :output_message_json,
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
                    "pending_approval_ids": json.dumps(record.pending_approval_ids),
                    "pending_delegation_ids": json.dumps(record.pending_delegation_ids),
                    "history_json": json.dumps(self._serialize_history(record.history)),
                    "input_message_json": json.dumps(self._serialize_message(record.input_message)),
                    "output_message_json": json.dumps(self._serialize_message(record.output_message)),
                    "error": record.error,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                },
            )
            await db.commit()

    async def get_run(self, run_id: str) -> RunRecord | None:
        """Load a RunRecord from orchestration_runs."""
        async with self._factory() as db:
            result = await db.execute(
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

        pending_approval_ids = row.get("pending_approval_ids") or []
        if isinstance(pending_approval_ids, str):
            pending_approval_ids = json.loads(pending_approval_ids)

        pending_delegation_ids = row.get("pending_delegation_ids") or []
        if isinstance(pending_delegation_ids, str):
            pending_delegation_ids = json.loads(pending_delegation_ids)

        return RunRecord(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            agent_name=row["agent_name"],
            graph_name=row["graph_name"],
            current_step_id=row["current_step_id"],
            context=RunContext(**context_data),
            metadata=metadata_data,
            pending_approval_ids=pending_approval_ids,
            pending_delegation_ids=pending_delegation_ids,
            history=self._deserialize_history(row.get("history_json")),
            input_message=self._deserialize_message(row.get("input_message_json")),
            output_message=self._deserialize_message(row.get("output_message_json")),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Approvals (DB-persisted) ──────────────────────────────────────

    async def save_approval(self, action: PendingAction) -> None:
        """INSERT into orchestration_pending_actions."""
        async with self._factory() as db:
            await db.execute(
                text("""
                    INSERT INTO orchestration_pending_actions
                        (id, run_id, step_id, action_type, action_name, status, created_at)
                    VALUES
                        (:id, :run_id, :step_id, :action_type, :action_name, :status, :created_at)
                    ON CONFLICT (id) DO UPDATE SET
                        status = :status
                """),
                {
                    "id": action.approval_request_id,
                    "run_id": action.run_id,
                    "step_id": action.step_id,
                    "action_type": action.action_type.value,
                    "action_name": action.action_name,
                    "status": "pending",
                    "created_at": action.created_at,
                },
            )
            await db.commit()

    async def get_approval(self, approval_id: str) -> PendingAction | None:
        """SELECT from orchestration_pending_actions."""
        async with self._factory() as db:
            result = await db.execute(
                text("SELECT * FROM orchestration_pending_actions WHERE id = :id"),
                {"id": approval_id},
            )
            row = result.mappings().first()
        if row is None:
            return None

        return PendingAction(
            approval_request_id=row["id"],
            run_id=row["run_id"],
            step_id=row["step_id"] or "",
            action_type=ApprovalSourceType(row["action_type"]),
            action_name=row["action_name"] or "",
            created_at=row["created_at"],
        )

    # ── Delegations (DB-persisted) ────────────────────────────────────

    async def save_delegation(self, request: DelegationRequest) -> None:
        """INSERT into orchestration_delegations."""
        async with self._factory() as db:
            await db.execute(
                text("""
                    INSERT INTO orchestration_delegations
                        (id, parent_run_id, child_agent_name, task, status,
                         delivery_status, timeout_sec, request_id, context_scope, created_at, updated_at)
                    VALUES
                        (:id, :parent_run_id, :child_agent_name, :task, :status,
                         :delivery_status, :timeout_sec, :request_id, :context_scope, :created_at, :updated_at)
                    ON CONFLICT (id) DO UPDATE SET
                        status = :status,
                        delivery_status = :delivery_status,
                        updated_at = :updated_at
                """),
                {
                    "id": request.id,
                    "parent_run_id": request.parent_run_id,
                    "child_agent_name": request.child_agent_name,
                    "task": request.task,
                    "status": "pending",
                    "delivery_status": DelegationDeliveryStatus.PENDING.value,
                    "timeout_sec": request.timeout_sec,
                    "request_id": request.request_id,
                    "context_scope": request.context_scope,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            )
            await db.commit()

    async def get_delegation(
        self, delegation_id: str
    ) -> DelegationRequest | None:
        """SELECT from orchestration_delegations."""
        async with self._factory() as db:
            result = await db.execute(
                text("SELECT * FROM orchestration_delegations WHERE id = :id"),
                {"id": delegation_id},
            )
            row = result.mappings().first()
        if row is None:
            return None

        return DelegationRequest(
            id=row["id"],
            parent_run_id=row["parent_run_id"],
            child_agent_name=row["child_agent_name"] or "",
            task=row["task"] or "",
            timeout_sec=row["timeout_sec"],
            request_id=row.get("request_id"),
            context_scope=row.get("context_scope"),
        )

    async def find_delegation_by_request_id(
        self, parent_run_id: str, request_id: str
    ) -> DelegationRequest | None:
        async with self._factory() as db:
            result = await db.execute(
                text(
                    "SELECT * FROM orchestration_delegations "
                    "WHERE parent_run_id = :parent_run_id AND request_id = :request_id "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {
                    "parent_run_id": parent_run_id,
                    "request_id": request_id,
                },
            )
            row = result.mappings().first()
        if row is None:
            return None
        return DelegationRequest(
            id=row["id"],
            parent_run_id=row["parent_run_id"],
            child_agent_name=row["child_agent_name"] or "",
            task=row["task"] or "",
            timeout_sec=row["timeout_sec"],
            request_id=row.get("request_id"),
            context_scope=row.get("context_scope"),
        )

    async def save_delegation_result(self, result: DelegationResult) -> None:
        """UPDATE orchestration_delegations with result columns."""
        output_json = None
        if result.output_message is not None:
            output_json = json.dumps(self._serialize_message(result.output_message))

        async with self._factory() as db:
            delivery_cursor = result.delivery_cursor
            if delivery_cursor is None:
                delivery_cursor = await self._next_delivery_cursor(db)
            delivery_status = (
                result.delivery_status.value
                if result.delivery_status is not None
                else DelegationDeliveryStatus.DELIVERED.value
            )
            await db.execute(
                text("""
                    UPDATE orchestration_delegations
                    SET child_run_id = :child_run_id,
                        status = :status,
                        delivery_status = CASE
                            WHEN delivery_status = 'acknowledged' THEN delivery_status
                            ELSE :delivery_status
                        END,
                        delivery_cursor = COALESCE(delivery_cursor, :delivery_cursor),
                        output_json = :output_json,
                        error = :error,
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": result.delegation_id,
                    "child_run_id": result.child_run_id,
                    "status": result.status.value,
                    "delivery_status": delivery_status,
                    "delivery_cursor": delivery_cursor,
                    "output_json": output_json,
                    "error": result.error,
                    "updated_at": datetime.utcnow(),
                },
            )
            await db.commit()
        result.delivery_cursor = delivery_cursor
        result.delivery_status = DelegationDeliveryStatus(delivery_status)

    async def get_delegation_result(
        self, delegation_id: str
    ) -> DelegationResult | None:
        """SELECT from orchestration_delegations where child_run_id IS NOT NULL."""
        async with self._factory() as db:
            result = await db.execute(
                text(
                    "SELECT * FROM orchestration_delegations "
                    "WHERE id = :id AND child_run_id IS NOT NULL"
                ),
                {"id": delegation_id},
            )
            row = result.mappings().first()
        if row is None:
            return None

        output_data = row["output_json"]
        if isinstance(output_data, str):
            output_data = json.loads(output_data)

        return DelegationResult(
            delegation_id=row["id"],
            child_run_id=row["child_run_id"],
            status=DelegationResultStatus(row["status"]),
            output_message=self._deserialize_message(output_data),
            error=row["error"],
            delivery_status=DelegationDeliveryStatus(
                row.get("delivery_status") or DelegationDeliveryStatus.DELIVERED.value
            ),
            delivery_cursor=row.get("delivery_cursor"),
        )

    # ── Events ────────────────────────────────────────────────────────

    async def list_delegation_results_since(
        self,
        *,
        parent_run_id: str,
        since_cursor: int,
        limit: int,
        include_acknowledged: bool = False,
    ) -> list[DelegationResult]:
        query = (
            "SELECT * FROM orchestration_delegations "
            "WHERE parent_run_id = :parent_run_id "
            "AND child_run_id IS NOT NULL "
            "AND COALESCE(delivery_cursor, 0) > :since_cursor "
        )
        if not include_acknowledged:
            query += "AND COALESCE(delivery_status, 'pending') <> 'acknowledged' "
        query += "ORDER BY delivery_cursor ASC, updated_at ASC LIMIT :limit"

        async with self._factory() as db:
            result = await db.execute(
                text(query),
                {
                    "parent_run_id": parent_run_id,
                    "since_cursor": since_cursor,
                    "limit": limit,
                },
            )
            rows = result.mappings().all()

        items: list[DelegationResult] = []
        for row in rows:
            output_data = row["output_json"]
            if isinstance(output_data, str):
                output_data = json.loads(output_data)
            items.append(
                DelegationResult(
                    delegation_id=row["id"],
                    child_run_id=row["child_run_id"] or "",
                    status=DelegationResultStatus(row["status"]),
                    output_message=self._deserialize_message(output_data),
                    error=row["error"],
                    delivery_status=DelegationDeliveryStatus(
                        row.get("delivery_status") or DelegationDeliveryStatus.DELIVERED.value
                    ),
                    delivery_cursor=row.get("delivery_cursor"),
                )
            )
        return items

    async def acknowledge_delegation_result(self, delegation_id: str) -> bool:
        async with self._factory() as db:
            result = await db.execute(
                text("""
                    UPDATE orchestration_delegations
                    SET delivery_status = :ack_status,
                        updated_at = :updated_at
                    WHERE id = :id
                      AND child_run_id IS NOT NULL
                      AND COALESCE(delivery_status, 'pending') <> :ack_status
                """),
                {
                    "id": delegation_id,
                    "ack_status": DelegationDeliveryStatus.ACKNOWLEDGED.value,
                    "updated_at": datetime.utcnow(),
                },
            )
            await db.commit()
            return (result.rowcount or 0) > 0

    async def append_event(self, event: OrchestrationEvent) -> None:
        """Persist an event to the DB and buffer it in-memory."""
        if event.run_id not in self._events:
            self._events[event.run_id] = []
        self._events[event.run_id].append(event)

        async with self._factory() as db:
            await db.execute(
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
            await db.commit()

    async def get_events(self, run_id: str) -> list[OrchestrationEvent]:
        """Return events from in-memory buffer first, fall back to DB."""
        if run_id in self._events:
            return list(self._events[run_id])

        async with self._factory() as db:
            result = await db.execute(
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

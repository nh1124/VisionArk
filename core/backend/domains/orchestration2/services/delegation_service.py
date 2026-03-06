"""Delegation adapter service (engine-external concerns).

Responsibilities:
- Resolve/create subagent sessions from ProjectAgent + parent chat session.
- Handle request_id idempotency before invoking engine delegation.
- Expose wait/receive helpers with cursor+ack handling.
- Maintain lightweight subagent conversation state for context restoration.
"""

from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domains.orchestration2.engine.models.common import MessageRole
from domains.orchestration2.engine.models.delegation import (
    DelegationDeliveryStatus,
    DelegationRequest,
    DelegationResult,
)
from domains.orchestration2.engine.models.message import Message
from shared.database import (
    OrchestrationDelegation,
    OrchestrationSubagentSession,
    ProjectAgent,
)


class DelegationService:
    """Adapter around AgentEngine for delivery/session/idempotency concerns."""

    def __init__(self, engine, db: AsyncSession | None) -> None:
        self._engine = engine
        self._db = db
        self._store = engine._store

    async def delegate(
        self,
        *,
        parent_run_id: str,
        child_agent: str,
        task: str,
        timeout_sec: int | None = None,
        mode: str = "sync",
        request_id: str | None = None,
        context_scope: str | None = None,
        runtime_metadata: dict[str, object] | None = None,
    ) -> DelegationResult | dict[str, object]:
        """Dispatch delegation in sync/async mode with request_id idempotency."""
        if request_id:
            existing = await self._store.find_delegation_by_request_id(
                parent_run_id,
                request_id,
            )
            if existing is not None:
                if mode == "async":
                    return {
                        "delegation_id": existing.id,
                        "status": "pending",
                        "request_id": request_id,
                        "idempotent_reuse": True,
                    }
                result = await self._engine.wait_delegation_result(
                    existing.id, timeout_sec=timeout_sec
                )
                await self._sync_subagent_state_from_result(result)
                return result

        subagent_session, child_history = await self._resolve_subagent_session(
            parent_run_id=parent_run_id,
            child_agent=child_agent,
        )
        subagent_session_id = subagent_session.id if subagent_session else None

        result = await self._engine.delegate_task(
            parent_run_id=parent_run_id,
            child_agent_name=child_agent,
            task=task,
            timeout_sec=timeout_sec,
            mode=mode,
            request_id=request_id,
            context_scope=context_scope,
            child_history=child_history,
            parent_metadata_override=runtime_metadata,
        )

        if mode == "async":
            assert isinstance(result, DelegationRequest)
            if subagent_session is not None:
                await self._link_subagent_session(
                    delegation_id=result.id,
                    subagent_session_id=subagent_session.id,
                )
                await self._append_user_task(
                    session=subagent_session,
                    delegation_id=result.id,
                    task=task,
                )
            return {
                "delegation_id": result.id,
                "status": "pending",
                "request_id": request_id,
                "subagent_session_id": subagent_session_id,
            }

        assert isinstance(result, DelegationResult)
        if subagent_session is not None:
            await self._link_subagent_session(
                delegation_id=result.delegation_id,
                subagent_session_id=subagent_session.id,
            )
        await self._sync_subagent_state_from_result(result)
        return result

    async def wait_for_delegation(
        self,
        *,
        delegation_id: str,
        timeout_sec: int | None = None,
        ack: bool = False,
    ) -> DelegationResult:
        result = await self._engine.wait_delegation_result(
            delegation_id,
            timeout_sec=timeout_sec,
        )
        await self._sync_subagent_state_from_result(result)
        if ack:
            await self._store.acknowledge_delegation_result(delegation_id)
            result.delivery_status = DelegationDeliveryStatus.ACKNOWLEDGED
        return result

    async def receive_results(
        self,
        *,
        parent_run_id: str,
        since_cursor: int = 0,
        limit: int = 20,
        ack: bool = False,
    ) -> dict[str, object]:
        results = await self._store.list_delegation_results_since(
            parent_run_id=parent_run_id,
            since_cursor=since_cursor,
            limit=limit,
            include_acknowledged=False,
        )

        max_cursor = since_cursor
        acked = 0
        payload_items: list[dict[str, object]] = []
        for result in results:
            await self._sync_subagent_state_from_result(result)

            if ack:
                changed = await self._store.acknowledge_delegation_result(
                    result.delegation_id
                )
                if changed:
                    acked += 1
                result.delivery_status = DelegationDeliveryStatus.ACKNOWLEDGED

            cursor = int(result.delivery_cursor or 0)
            if cursor > max_cursor:
                max_cursor = cursor

            payload_items.append(
                {
                    "delegation_id": result.delegation_id,
                    "child_run_id": result.child_run_id,
                    "status": result.status.value,
                    "output": result.output_message.content if result.output_message else "",
                    "error": result.error,
                    "delivery_status": (
                        result.delivery_status.value
                        if hasattr(result.delivery_status, "value")
                        else str(result.delivery_status)
                    ),
                    "delivery_cursor": result.delivery_cursor,
                }
            )

        return {
            "results": payload_items,
            "next_cursor": max_cursor,
            "count": len(payload_items),
            "acked": acked,
        }

    async def list_delegations(
        self,
        *,
        parent_run_id: str,
        limit: int = 20,
        status: str | None = None,
        child_agent: str | None = None,
        include_output: bool = False,
    ) -> dict[str, object]:
        if self._db is None:
            raise RuntimeError("db_session is required for list_delegations")

        query = select(OrchestrationDelegation).where(
            OrchestrationDelegation.parent_run_id == parent_run_id
        )
        if status:
            query = query.where(OrchestrationDelegation.status == status)
        if child_agent:
            query = query.where(OrchestrationDelegation.child_agent_name == child_agent)

        capped_limit = max(1, min(limit, 100))
        query = query.order_by(OrchestrationDelegation.created_at.desc()).limit(capped_limit)
        row = await self._db.execute(query)
        delegations = row.scalars().all()

        items: list[dict[str, object]] = []
        for delegation in delegations:
            output = ""
            if include_output and delegation.output_json:
                output_data = delegation.output_json
                if isinstance(output_data, str):
                    try:
                        output_data = json.loads(output_data)
                    except Exception:
                        output_data = {}
                if isinstance(output_data, dict):
                    output = str(output_data.get("content") or "")

            items.append(
                {
                    "delegation_id": delegation.id,
                    "parent_run_id": delegation.parent_run_id,
                    "child_agent": delegation.child_agent_name,
                    "child_run_id": delegation.child_run_id,
                    "status": delegation.status,
                    "delivery_status": delegation.delivery_status,
                    "delivery_cursor": delegation.delivery_cursor,
                    "request_id": delegation.request_id,
                    "context_scope": delegation.context_scope,
                    "task": delegation.task,
                    "error": delegation.error,
                    "created_at": (
                        delegation.created_at.isoformat()
                        if delegation.created_at is not None
                        else None
                    ),
                    "updated_at": (
                        delegation.updated_at.isoformat()
                        if delegation.updated_at is not None
                        else None
                    ),
                    "output": output,
                }
            )

        return {
            "delegations": items,
            "count": len(items),
        }

    async def _resolve_subagent_session(
        self,
        *,
        parent_run_id: str,
        child_agent: str,
    ) -> tuple[OrchestrationSubagentSession | None, list[Message] | None]:
        if self._db is None:
            return None, None
        parent_run = await self._store.get_run(parent_run_id)
        if parent_run is None:
            return None, None

        metadata = parent_run.metadata or {}
        parent_session_id = metadata.get("session_id")
        project_id = metadata.get("project_id")
        if not parent_session_id or not project_id:
            return None, None

        agent_res = await self._db.execute(
            select(ProjectAgent).where(
                ProjectAgent.project_id == project_id,
                ProjectAgent.status == "active",
                or_(
                    ProjectAgent.display_name == child_agent,
                    ProjectAgent.role_name == child_agent,
                ),
            )
        )
        project_agent = agent_res.scalars().first()
        if project_agent is None:
            return None, None

        session_res = await self._db.execute(
            select(OrchestrationSubagentSession).where(
                OrchestrationSubagentSession.parent_session_id == parent_session_id,
                OrchestrationSubagentSession.project_agent_id == project_agent.id,
            )
        )
        subagent_session = session_res.scalars().first()
        if subagent_session is None:
            subagent_session = OrchestrationSubagentSession(
                id=str(uuid4()),
                parent_session_id=parent_session_id,
                project_agent_id=project_agent.id,
                parent_run_id=parent_run_id,
                conversation_state_json={
                    "messages": [],
                    "summary": "",
                    "applied_delegation_ids": [],
                },
                status="active",
            )
            self._db.add(subagent_session)
            await self._db.commit()
        else:
            subagent_session.parent_run_id = parent_run_id
            subagent_session.status = "active"
            await self._db.commit()

        return subagent_session, self._history_from_state(subagent_session.conversation_state_json)

    def _history_from_state(
        self,
        state: dict | None,
    ) -> list[Message] | None:
        if not isinstance(state, dict):
            return None
        raw_messages = state.get("messages") or []
        history: list[Message] = []
        for item in raw_messages[-12:]:
            role_raw = str(item.get("role", "")).lower()
            content = str(item.get("content", ""))
            if not content:
                continue
            role = MessageRole.USER if role_raw == "user" else MessageRole.ASSISTANT
            history.append(Message(role=role, content=content))

        if history:
            return history

        summary = (state.get("summary") or "").strip()
        if summary:
            return [Message(role=MessageRole.SYSTEM, content=f"Subagent summary: {summary}")]
        return None

    async def _append_user_task(
        self,
        *,
        session: OrchestrationSubagentSession,
        delegation_id: str,
        task: str,
    ) -> None:
        if self._db is None:
            return
        state = dict(session.conversation_state_json or {})
        applied_ids = list(state.get("applied_delegation_ids") or [])
        if delegation_id in applied_ids:
            return

        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": task})
        state["messages"] = messages[-24:]
        state["summary"] = self._build_summary(state["messages"])
        state["applied_delegation_ids"] = applied_ids
        session.conversation_state_json = state
        await self._db.commit()

    async def _sync_subagent_state_from_result(self, result: DelegationResult) -> None:
        if self._db is None:
            return
        delegation = await self._get_delegation_row(result.delegation_id)
        if delegation is None or not delegation.subagent_session_id:
            return

        row = await self._db.execute(
            select(OrchestrationSubagentSession).where(
                OrchestrationSubagentSession.id == delegation.subagent_session_id
            )
        )
        session = row.scalars().first()
        if session is None:
            return

        state = dict(session.conversation_state_json or {})
        applied_ids = list(state.get("applied_delegation_ids") or [])
        if result.delegation_id in applied_ids:
            # Ensure latest_child_run_id is still refreshed when available.
            if result.child_run_id:
                session.latest_child_run_id = result.child_run_id
                await self._db.commit()
            return

        messages = list(state.get("messages") or [])
        delegation_task = (delegation.task or "").strip()
        if delegation_task and (
            not messages or messages[-1].get("content") != delegation_task
        ):
            messages.append({"role": "user", "content": delegation_task})

        assistant_text = ""
        if result.output_message is not None:
            assistant_text = result.output_message.content
        elif result.error:
            assistant_text = f"[delegation_error] {result.error}"
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})

        applied_ids.append(result.delegation_id)
        state["messages"] = messages[-24:]
        state["summary"] = self._build_summary(state["messages"])
        state["applied_delegation_ids"] = applied_ids[-200:]
        session.conversation_state_json = state
        if result.child_run_id:
            session.latest_child_run_id = result.child_run_id
        await self._db.commit()

    async def _get_delegation_row(
        self,
        delegation_id: str,
    ) -> OrchestrationDelegation | None:
        if self._db is None:
            return None
        row = await self._db.execute(
            select(OrchestrationDelegation).where(
                OrchestrationDelegation.id == delegation_id
            )
        )
        return row.scalars().first()

    async def _link_subagent_session(
        self,
        *,
        delegation_id: str,
        subagent_session_id: str,
    ) -> None:
        if self._db is None:
            return
        await self._db.execute(
            update(OrchestrationDelegation)
            .where(OrchestrationDelegation.id == delegation_id)
            .values(subagent_session_id=subagent_session_id)
        )
        await self._db.commit()

    @staticmethod
    def _build_summary(messages: list[dict]) -> str:
        if not messages:
            return ""
        recent = messages[-6:]
        summary_parts: list[str] = []
        for item in recent:
            role = str(item.get("role", "assistant"))
            content = str(item.get("content", "")).strip().replace("\n", " ")
            if not content:
                continue
            summary_parts.append(f"{role}: {content[:140]}")
        return " | ".join(summary_parts)

    @staticmethod
    def encode_json(payload: dict[str, object]) -> str:
        return json.dumps(payload, ensure_ascii=False)

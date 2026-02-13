"""Routing tools: multicast, subscribe/unsubscribe intents."""

from __future__ import annotations

import copy
import uuid

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, get_user_id, make_result


class SubscribeIntentTool:
    definition = ToolDef(
        name="subscribe_to_intent",
        description=(
            "Subscribe to message patterns (regex) or semantic intents for AI-based routing. "
            "The System Router will notify you when a relevant message is detected."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern for matching"},
                "intent_description": {"type": "string", "description": "Natural language intent description"},
                "description": {"type": "string", "description": "User-facing label"},
                "session_bound": {"type": "boolean", "description": "Auto-remove when session archives"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        pattern = call.arguments.get("pattern")
        intent_desc = call.arguments.get("intent_description")
        description = call.arguments.get("description")
        session_bound = call.arguments.get("session_bound", True)

        if not pattern and not intent_desc:
            return fail(call, "Either 'pattern' or 'intent_description' must be provided.")

        agent_id = ctx.metadata.get("agent_id")
        session_id = ctx.metadata.get("session_id") if session_bound else None
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from sqlalchemy.orm.attributes import flag_modified
            from shared.database import ProjectAgent

            res = await db.execute(select(ProjectAgent).filter(ProjectAgent.id == agent_id))
            agent = res.scalars().first()
            if not agent:
                return fail(call, f"Agent {agent_id} not found.")

            meta = copy.deepcopy(agent.meta_payload or {})
            sub_id = f"sub_{uuid.uuid4().hex[:8]}"

            if pattern:
                patterns = meta.get("trigger_patterns", [])
                if not any(p.get("value") == pattern for p in patterns if isinstance(p, dict)):
                    patterns.append({"id": sub_id, "value": pattern, "session_id": session_id, "description": description})
                    meta["trigger_patterns"] = patterns

            if intent_desc:
                interests = meta.get("semantic_interests", [])
                if not any(i.get("value") == intent_desc for i in interests if isinstance(i, dict)):
                    interests.append({"id": sub_id, "value": intent_desc, "session_id": session_id, "description": description})
                    meta["semantic_interests"] = interests

            agent.meta_payload = meta
            flag_modified(agent, "meta_payload")
            await db.commit()

            try:
                from api.router import Router
                await Router.initialize_default_hooks()
            except Exception:
                pass

            return make_result(call, f"Subscribed (ID: {sub_id}).")
        except Exception as e:
            await db.rollback()
            return fail(call, f"Subscribe failed: {e}")


class UnsubscribeIntentTool:
    definition = ToolDef(
        name="unsubscribe_from_intent",
        description="Remove a subscription by ID, pattern, or intent description.",
        parameters={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string", "description": "Subscription ID to remove"},
                "pattern": {"type": "string", "description": "Regex pattern to remove"},
                "intent_description": {"type": "string", "description": "Semantic intent to remove"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        sub_id = call.arguments.get("subscription_id")
        pattern = call.arguments.get("pattern")
        intent_desc = call.arguments.get("intent_description")

        if not sub_id and not pattern and not intent_desc:
            return fail(call, "Provide subscription_id, pattern, or intent_description.")

        agent_id = ctx.metadata.get("agent_id")
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from sqlalchemy.orm.attributes import flag_modified
            from shared.database import ProjectAgent

            res = await db.execute(select(ProjectAgent).filter(ProjectAgent.id == agent_id))
            agent = res.scalars().first()
            if not agent:
                return fail(call, f"Agent {agent_id} not found.")

            meta = copy.deepcopy(agent.meta_payload or {})
            removed = False

            def filter_list(key, match_val, by_id=False):
                nonlocal removed
                lst = meta.get(key, [])
                new_lst = []
                for item in lst:
                    if not isinstance(item, dict):
                        continue
                    if by_id and item.get("id") == match_val:
                        removed = True
                        continue
                    if not by_id and item.get("value") == match_val:
                        removed = True
                        continue
                    new_lst.append(item)
                return new_lst

            if sub_id:
                meta["trigger_patterns"] = filter_list("trigger_patterns", sub_id, by_id=True)
                meta["semantic_interests"] = filter_list("semantic_interests", sub_id, by_id=True)
            else:
                if pattern:
                    meta["trigger_patterns"] = filter_list("trigger_patterns", pattern)
                if intent_desc:
                    meta["semantic_interests"] = filter_list("semantic_interests", intent_desc)

            if removed:
                agent.meta_payload = meta
                flag_modified(agent, "meta_payload")
                await db.commit()

                try:
                    from api.router import Router
                    await Router.initialize_default_hooks()
                except Exception:
                    pass

                return make_result(call, "Unsubscribed successfully.")

            return fail(call, "No matching subscription found.")
        except Exception as e:
            await db.rollback()
            return fail(call, f"Unsubscribe failed: {e}")


class ListSubscriptionsTool:
    definition = ToolDef(
        name="list_my_subscriptions",
        description="List all active subscriptions (intents and regex hooks) for your node.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        agent_id = ctx.metadata.get("agent_id")
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent

            res = await db.execute(select(ProjectAgent).filter(ProjectAgent.id == agent_id))
            agent = res.scalars().first()
            if not agent:
                return fail(call, "Agent not found.")

            meta = agent.meta_payload or {}
            patterns = meta.get("trigger_patterns", [])
            interests = meta.get("semantic_interests", [])

            if not patterns and not interests:
                return make_result(call, "No active subscriptions.")

            lines = ["Active Subscriptions:"]
            if patterns:
                lines.append("\nRegex Patterns:")
                for p in patterns:
                    if isinstance(p, dict):
                        lines.append(f"  - ID: {p.get('id')} | Pattern: {p.get('value')}")

            if interests:
                lines.append("\nSemantic Interests:")
                for i in interests:
                    if isinstance(i, dict):
                        lines.append(f"  - ID: {i.get('id')} | Intent: {i.get('value')}")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list subscriptions: {e}")

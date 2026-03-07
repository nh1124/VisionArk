"""System tools: agent management, project operations, timers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, get_user_id, make_result

_AES_PRESET_RECURRING_RULES = {"@hourly", "@daily", "@weekly"}


def _validate_iana_timezone(name: str) -> str:
    if not name:
        return "UTC"
    try:
        ZoneInfo(name)
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {name}") from exc
    return name


def _next_run_for_preset(rule: str, timezone_name: str, after_utc: datetime | None = None) -> datetime:
    base = after_utc or datetime.utcnow()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    else:
        base = base.astimezone(timezone.utc)

    tz = ZoneInfo(timezone_name)
    local = base.astimezone(tz)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)

    if rule == "@hourly":
        candidate_local = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    elif rule == "@daily":
        candidate_local = day_start + timedelta(days=1)
    elif rule == "@weekly":
        days_until_sunday = (6 - day_start.weekday()) % 7
        candidate_local = day_start + timedelta(days=days_until_sunday)
        if candidate_local <= local:
            candidate_local += timedelta(days=7)
    else:
        raise ValueError(f"Unsupported recurring rule: {rule}")

    return candidate_local.astimezone(timezone.utc).replace(tzinfo=None)


class ListAgentsTool:
    definition = ToolDef(
        name="list_agents",
        description="List all available agents (System, Members, Peer Projects) for communication.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent, Project

            res_s = await db.execute(select(ProjectAgent).filter(ProjectAgent.agent_type == "SYSTEM", ProjectAgent.status == "active"))
            systems = res_s.scalars().all()

            res_m = await db.execute(select(ProjectAgent).filter(ProjectAgent.project_id == project_id, ProjectAgent.agent_type == "MEMBER", ProjectAgent.status == "active"))
            members = res_m.scalars().all()

            res_p = await db.execute(
                select(ProjectAgent).join(Project, ProjectAgent.project_id == Project.id).filter(
                    Project.user_id == user_id,
                    ProjectAgent.agent_type == "PROJECT",
                    ProjectAgent.status == "active",
                )
            )
            peers = res_p.scalars().all()

            lines = [f"Found {len(systems) + len(members) + len(peers)} available agents:"]
            for a in systems + members + peers:
                lines.append(f"- [{a.agent_type}] {a.id}: {a.display_name} ({a.role_name}) - {a.description or 'No description'}")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list agents: {e}")


class GetAgentProfileTool:
    definition = ToolDef(
        name="get_agent_profile",
        description="Retrieve detailed profile and capabilities for a specific agent ID.",
        parameters={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "UUID of the agent to inspect"},
            },
            "required": ["agent_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        agent_id = call.arguments.get("agent_id", "")
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent

            res = await db.execute(select(ProjectAgent).filter(ProjectAgent.id == agent_id))
            agent = res.scalars().first()
            if not agent:
                return fail(call, f"Agent {agent_id} not found.")

            info = (
                f"Agent: {agent.display_name} ({agent.role_name})\n"
                f"Type: {agent.agent_type}\n"
                f"Description: {agent.description or 'None'}\n"
                f"Tools: {agent.tools or []}\n"
                f"Status: {agent.status}"
            )
            return make_result(call, info)
        except Exception as e:
            return fail(call, f"Failed to get agent profile: {e}")


class ListUserProjectsTool:
    definition = ToolDef(
        name="list_user_projects",
        description="List all user projects with status and priority.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import Project

            res = await db.execute(select(Project).filter(Project.user_id == user_id).order_by(Project.priority))
            projects = res.scalars().all()

            lines = [f"Found {len(projects)} projects:"]
            for p in projects:
                lines.append(f"- [{p.status}] {p.name} (id: {p.id}, priority: {p.priority})")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list projects: {e}")


class UpdateProjectTool:
    definition = ToolDef(
        name="update_project",
        description="Update project metadata (name, status, priority).",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "New project name"},
                "status": {"type": "string", "description": "New status: active, paused, archived"},
                "priority": {"type": "integer", "description": "Priority 1-5"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import Project

            res = await db.execute(select(Project).filter(Project.id == project_id))
            project = res.scalars().first()
            if not project:
                return fail(call, "Project not found.")

            if "name" in call.arguments:
                project.name = call.arguments["name"]
            if "status" in call.arguments:
                project.status = call.arguments["status"]
            if "priority" in call.arguments:
                project.priority = call.arguments["priority"]

            await db.commit()
            return make_result(call, f"Project '{project.name}' updated.")
        except Exception as e:
            return fail(call, f"Failed to update project: {e}")


class GetProjectHealthTool:
    definition = ToolDef(
        name="get_project_health",
        description="Analyze project health (agents, activity, status).",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            from sqlalchemy import select, func
            from shared.database import ProjectAgent, ChatMessage, ChatSession

            agents_res = await db.execute(select(func.count()).select_from(ProjectAgent).filter(ProjectAgent.project_id == project_id))
            agent_count = agents_res.scalar() or 0

            sessions_res = await db.execute(select(func.count()).select_from(ChatSession).filter(ChatSession.project_id == project_id))
            session_count = sessions_res.scalar() or 0

            info = (
                f"Project Health Report:\n"
                f"- Agents: {agent_count}\n"
                f"- Sessions: {session_count}\n"
                f"- Status: active"
            )
            return make_result(call, info)
        except Exception as e:
            return fail(call, f"Health check failed: {e}")


class SetTimerTool:
    definition = ToolDef(
        name="set_timer",
        description="Set a timer to notify the user after specified minutes.",
        parameters={
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Minutes until notification"},
                "message": {"type": "string", "description": "Notification message"},
            },
            "required": ["minutes", "message"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        minutes = call.arguments.get("minutes", 1)
        message = call.arguments.get("message", "Timer expired")
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            from shared.database import ScheduledTask

            task = ScheduledTask(
                id=str(uuid.uuid4()),
                user_id=user_id,
                project_id=project_id,
                task_type="SYSTEM_TIMER",
                payload={
                    "title": "Timer",
                    "content": message,
                    "link": f"/projects/{project_id}" if project_id else None,
                },
                scheduled_at=datetime.utcnow() + timedelta(minutes=minutes),
                status="pending",
            )
            db.add(task)
            await db.flush()

            return make_result(call, f"Timer set for {minutes} minutes: {message}")
        except Exception as e:
            return fail(call, f"Failed to set timer: {e}")


class ScheduleRecurringPromptTool:
    definition = ToolDef(
        name="schedule_recurring_prompt",
        description=(
            "Schedule a recurring prompt execution for the current project. "
            "Uses cron + timezone and enqueues POST_MESSAGE task on each run."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Prompt/message to run on each schedule"},
                "cron": {"type": "string", "description": "Recurring rule (@hourly/@daily/@weekly)"},
                "timezone": {"type": "string", "description": "IANA timezone name (e.g. 'Asia/Tokyo', 'UTC')"},
                "session_id": {"type": "string", "description": "Optional target chat session id"},
                "first_run_after": {
                    "type": "string",
                    "description": "Optional ISO datetime anchor. Next run will be computed after this timestamp.",
                },
            },
            "required": ["prompt", "cron"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        args = call.arguments
        prompt = str(args.get("prompt", "")).strip()
        cron = str(args.get("cron", "")).strip()
        timezone_name = str(args.get("timezone", "UTC") or "UTC").strip()
        session_id = args.get("session_id")
        first_run_after_raw = args.get("first_run_after")

        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        if not prompt:
            return fail(call, "prompt is required.")
        if not cron:
            return fail(call, "cron is required.")
        if cron not in _AES_PRESET_RECURRING_RULES:
            return fail(
                call,
                "Unsupported recurring rule. For AES compatibility, use one of: @hourly, @daily, @weekly.",
            )

        try:
            from domains.automation.aes_scheduler_service import AESSchedulerService

            timezone_name = _validate_iana_timezone(timezone_name)

            anchor = datetime.utcnow()
            if first_run_after_raw:
                raw = str(first_run_after_raw).strip()
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                anchor = dt

            next_run = _next_run_for_preset(
                rule=cron,
                timezone_name=timezone_name,
                after_utc=anchor,
            )

            payload = {
                "message": prompt,
                "timezone": timezone_name,
            }
            if session_id:
                payload["session_id"] = str(session_id)

            scheduler = AESSchedulerService(db)
            task_id = await scheduler.create_task(
                user_id=user_id,
                task_type="POST_MESSAGE",
                scheduled_at=next_run,
                project_id=project_id,
                payload=payload,
                recurring_rule=cron,
            )

            return make_result(
                call,
                (
                    "Recurring prompt scheduled.\n"
                    f"- task_id: {task_id}\n"
                    f"- task_type: POST_MESSAGE\n"
                    f"- cron: {cron}\n"
                    f"- timezone: {timezone_name}\n"
                    f"- next_run_at_utc: {next_run.isoformat()}\n"
                    f"- project_id: {project_id}"
                ),
            )
        except Exception as e:
            return fail(call, f"Failed to schedule recurring prompt: {e}")


class ScheduleMonitorJobTool:
    definition = ToolDef(
        name="schedule_monitor_job",
        description=(
            "Create a monitor job. "
            "timezone must be IANA (e.g. 'Asia/Tokyo'). "
            "detector supports {expected_status:int=200, max_latency_ms:int?, contains_any:[str]?, not_contains_any:[str]?}. "
            "notify supports {channel:'in_app', agent_delivery:{enabled:bool, project_id:str, session_id:str?, min_severity:'warn'|'critical'?}}."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "source_type": {"type": "string", "description": "URL/HTTP etc."},
                "source_config": {"type": "object", "description": "Source settings, e.g. {url, timeout_seconds}"},
                "cron": {"type": "string", "description": "Cron rule (5 fields or @daily/@hourly/@weekly)"},
                "timezone": {"type": "string", "description": "IANA timezone name (e.g. 'Asia/Tokyo', 'UTC')."},
                "detector": {
                    "type": "object",
                    "description": "Rule detector options: expected_status, max_latency_ms, contains_any[], not_contains_any[].",
                },
                "notify": {
                    "type": "object",
                    "description": "Notification options: channel='in_app', optional agent_delivery{enabled, project_id, session_id, min_severity}.",
                },
                "cooldown_seconds": {"type": "integer"},
            },
            "required": ["name", "source_config", "cron"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        args = call.arguments

        try:
            from domains.monitoring.service import MonitoringService

            service = MonitoringService(db)
            job = await service.create_job(
                user_id=user_id,
                payload={
                    "name": args.get("name"),
                    "source_type": args.get("source_type", "URL"),
                    "source_config": args.get("source_config", {}),
                    "schedule_cron": args.get("cron"),
                    "timezone": args.get("timezone", "UTC"),
                    "detector_type": "RULE_BASED",
                    "detector_config": args.get("detector", {}),
                    "notification_config": args.get("notify", {"channel": "in_app"}),
                    "cooldown_seconds": args.get("cooldown_seconds", 0),
                },
            )
            return make_result(
                call,
                (
                    f"Monitor job created.\n"
                    f"- monitor_job_id: {job.id}\n"
                    f"- next_run_at: {job.next_run_at.isoformat() if job.next_run_at else 'none'}\n"
                    f"- status: {'active' if job.is_active else 'paused'}"
                ),
            )
        except Exception as e:
            return fail(call, f"Failed to schedule monitor job: {e}")


class ListMonitorJobsTool:
    definition = ToolDef(
        name="list_monitor_jobs",
        description="List monitor jobs and their latest status.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "active | paused"},
                "source_type": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        args = call.arguments

        try:
            from domains.monitoring.service import MonitoringService

            is_active = None
            status = args.get("status")
            if status == "active":
                is_active = True
            elif status == "paused":
                is_active = False

            service = MonitoringService(db)
            jobs = await service.list_jobs(
                user_id=user_id,
                is_active=is_active,
                source_type=args.get("source_type"),
                limit=int(args.get("limit", 20)),
            )

            if not jobs:
                return make_result(call, "No monitor jobs found.")

            lines = [f"Found {len(jobs)} monitor jobs:"]
            for job in jobs:
                lines.append(
                    f"- {job.id} | {job.name} | active={job.is_active} | last={job.last_status or 'none'} | next={job.next_run_at}"
                )
            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list monitor jobs: {e}")


class UpdateMonitorJobTool:
    definition = ToolDef(
        name="update_monitor_job",
        description="Update settings for an existing monitor job.",
        parameters={
            "type": "object",
            "properties": {
                "monitor_job_id": {"type": "string"},
                "name": {"type": "string"},
                "source_config": {"type": "object"},
                "cron": {"type": "string"},
                "timezone": {"type": "string", "description": "IANA timezone name (e.g. 'Asia/Tokyo', 'UTC')."},
                "detector": {
                    "type": "object",
                    "description": "Rule detector options: expected_status, max_latency_ms, contains_any[], not_contains_any[].",
                },
                "notify": {
                    "type": "object",
                    "description": "Notification options: channel='in_app', optional agent_delivery{enabled, project_id, session_id, min_severity}.",
                },
                "cooldown_seconds": {"type": "integer"},
            },
            "required": ["monitor_job_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        args = call.arguments
        monitor_job_id = args.get("monitor_job_id")

        try:
            from domains.monitoring.service import MonitoringService

            service = MonitoringService(db)
            job = await service.get_job(user_id, monitor_job_id)
            if not job:
                return fail(call, f"Monitor job not found: {monitor_job_id}")

            payload = {}
            if "name" in args:
                payload["name"] = args["name"]
            if "source_config" in args:
                payload["source_config"] = args["source_config"]
            if "cron" in args:
                payload["schedule_cron"] = args["cron"]
            if "timezone" in args:
                payload["timezone"] = args["timezone"]
            if "detector" in args:
                payload["detector_config"] = args["detector"]
            if "notify" in args:
                payload["notification_config"] = args["notify"]
            if "cooldown_seconds" in args:
                payload["cooldown_seconds"] = args["cooldown_seconds"]

            job = await service.update_job(job, payload)
            return make_result(
                call,
                f"Monitor job updated: {job.id} (next_run_at={job.next_run_at})",
            )
        except Exception as e:
            return fail(call, f"Failed to update monitor job: {e}")


class PauseMonitorJobTool:
    definition = ToolDef(
        name="pause_monitor_job",
        description="Pause a monitor job.",
        parameters={
            "type": "object",
            "properties": {
                "monitor_job_id": {"type": "string"},
            },
            "required": ["monitor_job_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        monitor_job_id = call.arguments.get("monitor_job_id")

        try:
            from domains.monitoring.service import MonitoringService

            service = MonitoringService(db)
            job = await service.get_job(user_id, monitor_job_id)
            if not job:
                return fail(call, f"Monitor job not found: {monitor_job_id}")
            await service.pause_job(job)
            return make_result(call, f"Paused monitor job: {monitor_job_id}")
        except Exception as e:
            return fail(call, f"Failed to pause monitor job: {e}")


class ResumeMonitorJobTool:
    definition = ToolDef(
        name="resume_monitor_job",
        description="Resume a paused monitor job.",
        parameters={
            "type": "object",
            "properties": {
                "monitor_job_id": {"type": "string"},
            },
            "required": ["monitor_job_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        monitor_job_id = call.arguments.get("monitor_job_id")

        try:
            from domains.monitoring.service import MonitoringService

            service = MonitoringService(db)
            job = await service.get_job(user_id, monitor_job_id)
            if not job:
                return fail(call, f"Monitor job not found: {monitor_job_id}")
            job = await service.resume_job(job)
            return make_result(call, f"Resumed monitor job: {monitor_job_id} (next_run_at={job.next_run_at})")
        except Exception as e:
            return fail(call, f"Failed to resume monitor job: {e}")


class TestMonitorJobOnceTool:
    definition = ToolDef(
        name="test_monitor_job_once",
        description="Run one immediate collect/detect cycle for a monitor job.",
        parameters={
            "type": "object",
            "properties": {
                "monitor_job_id": {"type": "string"},
            },
            "required": ["monitor_job_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        monitor_job_id = call.arguments.get("monitor_job_id")

        try:
            from domains.monitoring.service import MonitoringService

            service = MonitoringService(db)
            job = await service.get_job(user_id, monitor_job_id)
            if not job:
                return fail(call, f"Monitor job not found: {monitor_job_id}")

            run = await service.test_job_once(user_id, monitor_job_id)
            return make_result(
                call,
                f"Test run completed: run_id={run.id}, status={run.status}, severity={run.severity or 'none'}",
            )
        except Exception as e:
            return fail(call, f"Failed to test monitor job: {e}")


class ListMonitorJobRunsTool:
    definition = ToolDef(
        name="list_monitor_job_runs",
        description="List recent run results for a monitor job.",
        parameters={
            "type": "object",
            "properties": {
                "monitor_job_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["monitor_job_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        monitor_job_id = call.arguments.get("monitor_job_id")
        limit = int(call.arguments.get("limit", 20))

        try:
            from domains.monitoring.service import MonitoringService

            service = MonitoringService(db)
            job = await service.get_job(user_id, monitor_job_id)
            if not job:
                return fail(call, f"Monitor job not found: {monitor_job_id}")

            runs = await service.list_job_runs(user_id, monitor_job_id, limit=max(1, min(limit, 50)))
            if not runs:
                return make_result(call, "No monitor runs found.")

            lines = [f"Recent runs for {job.name} ({job.id}):"]
            for run in runs:
                lines.append(
                    f"- {run.started_at} | status={run.status} | severity={run.severity or '-'} | latency_ms={run.latency_ms or '-'} | run_id={run.id}"
                )
                if run.error_log:
                    lines.append(f"  error: {run.error_log}")
            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list monitor job runs: {e}")


class ListMonitorAlertsTool:
    definition = ToolDef(
        name="list_monitor_alerts",
        description="List recent monitor alerts (optionally filtered by monitor_job_id/severity).",
        parameters={
            "type": "object",
            "properties": {
                "monitor_job_id": {"type": "string"},
                "severity": {"type": "string", "description": "warn|critical"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        monitor_job_id = call.arguments.get("monitor_job_id")
        severity = call.arguments.get("severity")
        limit = int(call.arguments.get("limit", 20))

        try:
            from domains.monitoring.service import MonitoringService

            service = MonitoringService(db)
            alerts = await service.list_alerts(
                user_id=user_id,
                monitor_job_id=monitor_job_id,
                severity=severity,
                limit=max(1, min(limit, 100)),
            )
            if not alerts:
                return make_result(call, "No monitor alerts found.")

            lines = [f"Recent monitor alerts: {len(alerts)}"]
            for alert in alerts:
                lines.append(
                    f"- {alert.triggered_at} | severity={alert.severity} | status={alert.notification_status} | job_id={alert.monitor_job_id} | alert_id={alert.id}"
                )
                lines.append(f"  reason: {alert.reason}")
            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list monitor alerts: {e}")


class RaiseContinueTool:
    definition = ToolDef(
        name="raise_continue",
        description="Signal the reasoning loop to continue processing.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        return make_result(call, "Continue signal acknowledged.")

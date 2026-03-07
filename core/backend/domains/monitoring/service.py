from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.automation.aes_scheduler_service import AESSchedulerService
from domains.monitoring.collectors.base import get_collector
from domains.monitoring.detectors.base import get_detector
from domains.monitoring.models import DetectionResult
from domains.monitoring.notifiers.base import get_notifier
from domains.monitoring.schedule import next_run_at_utc, normalize_cron, validate_schedule, validate_timezone
from shared.database import (
    MonitorAlert,
    MonitorJob,
    MonitorJobRun,
    ScheduledTask,
    ScheduledTaskStatus,
)


class MonitoringService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, user_id: str, payload: Dict[str, Any]) -> MonitorJob:
        schedule_cron = normalize_cron(payload.get("schedule_cron", ""))
        timezone = validate_timezone(payload.get("timezone", "UTC"))
        validate_schedule(schedule_cron, timezone)

        now = datetime.utcnow()
        is_active = bool(payload.get("is_active", True))
        valid_from = payload.get("valid_from")
        valid_until = payload.get("valid_until")
        next_run_at = (
            self._compute_next_run(schedule_cron, timezone, valid_from, valid_until, now)
            if is_active
            else None
        )

        job = MonitorJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=payload["name"],
            source_type=str(payload.get("source_type", "URL")).upper(),
            source_config=payload.get("source_config") or {},
            schedule_cron=schedule_cron,
            timezone=timezone,
            detector_type=str(payload.get("detector_type", "RULE_BASED")).upper(),
            detector_config=payload.get("detector_config") or {},
            notification_config=payload.get("notification_config") or {"channel": "in_app"},
            cooldown_seconds=max(0, int(payload.get("cooldown_seconds", 0))),
            max_retries=max(0, int(payload.get("max_retries", 2))),
            retry_backoff_seconds=max(5, int(payload.get("retry_backoff_seconds", 60))),
            is_active=is_active,
            valid_from=valid_from,
            valid_until=valid_until,
            next_run_at=next_run_at,
        )

        self.db.add(job)
        await self.db.flush()

        committed = await self._replace_pending_aes_task(job)
        if not committed:
            await self.db.commit()

        await self.db.refresh(job)
        return job

    async def update_job(self, job: MonitorJob, payload: Dict[str, Any]) -> MonitorJob:
        schedule_cron = normalize_cron(payload.get("schedule_cron", job.schedule_cron))
        timezone = validate_timezone(payload.get("timezone", job.timezone))
        validate_schedule(schedule_cron, timezone)

        job.name = payload.get("name", job.name)
        job.source_type = str(payload.get("source_type", job.source_type)).upper()
        job.source_config = payload.get("source_config", job.source_config)
        job.schedule_cron = schedule_cron
        job.timezone = timezone
        job.detector_type = str(payload.get("detector_type", job.detector_type)).upper()
        job.detector_config = payload.get("detector_config", job.detector_config)
        job.notification_config = payload.get("notification_config", job.notification_config)
        job.cooldown_seconds = max(0, int(payload.get("cooldown_seconds", job.cooldown_seconds)))
        job.max_retries = max(0, int(payload.get("max_retries", job.max_retries)))
        job.retry_backoff_seconds = max(
            5, int(payload.get("retry_backoff_seconds", job.retry_backoff_seconds))
        )
        job.is_active = bool(payload.get("is_active", job.is_active))
        job.valid_from = payload.get("valid_from", job.valid_from)
        job.valid_until = payload.get("valid_until", job.valid_until)

        now = datetime.utcnow()
        if job.is_active:
            job.next_run_at = self._compute_next_run(
                job.schedule_cron,
                job.timezone,
                job.valid_from,
                job.valid_until,
                now,
            )
        else:
            job.next_run_at = None

        committed = await self._replace_pending_aes_task(job)
        if not committed:
            await self.db.commit()

        await self.db.refresh(job)
        return job

    async def pause_job(self, job: MonitorJob) -> MonitorJob:
        job.is_active = False
        job.next_run_at = None

        committed = await self._replace_pending_aes_task(job)
        if not committed:
            await self.db.commit()

        await self.db.refresh(job)
        return job

    async def resume_job(self, job: MonitorJob) -> MonitorJob:
        now = datetime.utcnow()
        job.is_active = True
        job.next_run_at = self._compute_next_run(
            job.schedule_cron,
            job.timezone,
            job.valid_from,
            job.valid_until,
            now,
        )

        committed = await self._replace_pending_aes_task(job)
        if not committed:
            await self.db.commit()

        await self.db.refresh(job)
        return job

    async def get_job(self, user_id: str, job_id: str) -> Optional[MonitorJob]:
        stmt = select(MonitorJob).filter(
            MonitorJob.id == job_id,
            MonitorJob.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_jobs(
        self,
        user_id: str,
        *,
        is_active: Optional[bool] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[MonitorJob]:
        stmt = select(MonitorJob).filter(MonitorJob.user_id == user_id)
        if is_active is not None:
            stmt = stmt.filter(MonitorJob.is_active == is_active)
        if source_type:
            stmt = stmt.filter(MonitorJob.source_type == source_type.upper())

        stmt = stmt.order_by(desc(MonitorJob.created_at)).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_job_runs(self, user_id: str, monitor_job_id: str, limit: int = 50) -> list[MonitorJobRun]:
        stmt = (
            select(MonitorJobRun)
            .join(MonitorJob, MonitorJobRun.monitor_job_id == MonitorJob.id)
            .filter(
                MonitorJobRun.monitor_job_id == monitor_job_id,
                MonitorJob.user_id == user_id,
            )
            .order_by(desc(MonitorJobRun.started_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_alerts(
        self,
        user_id: str,
        *,
        monitor_job_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> list[MonitorAlert]:
        stmt = select(MonitorAlert).filter(MonitorAlert.user_id == user_id)
        if monitor_job_id:
            stmt = stmt.filter(MonitorAlert.monitor_job_id == monitor_job_id)
        if severity:
            stmt = stmt.filter(MonitorAlert.severity == severity)

        stmt = stmt.order_by(desc(MonitorAlert.triggered_at)).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def execute_monitor_check(
        self,
        *,
        user_id: str,
        monitor_job_id: str,
        monitor_run_id: Optional[str] = None,
        reschedule: bool = True,
    ) -> MonitorJobRun:
        job = await self.get_job(user_id, monitor_job_id)
        if not job:
            raise ValueError(f"Monitor job not found: {monitor_job_id}")

        run: Optional[MonitorJobRun] = None
        if monitor_run_id:
            run = await self.db.get(MonitorJobRun, monitor_run_id)
            if run and run.monitor_job_id != monitor_job_id:
                raise ValueError("monitor_run_id does not belong to monitor_job_id")

        if not run:
            run = MonitorJobRun(
                id=str(uuid.uuid4()),
                monitor_job_id=job.id,
                user_id=user_id,
                status="processing",
                retry_count=job.consecutive_failures,
                started_at=datetime.utcnow(),
            )
            self.db.add(run)
            await self.db.flush()

        started = datetime.utcnow()

        if not job.is_active:
            run.status = "skipped"
            run.severity = "normal"
            run.result_payload = {"reason": "job_inactive"}
        elif not self._is_within_valid_window(job, started):
            run.status = "skipped"
            run.severity = "normal"
            run.result_payload = {"reason": "outside_valid_window"}
        else:
            try:
                collector = get_collector(job.source_type)
                detector = get_detector(job.detector_type)

                collected = await collector.collect(job)
                detected = detector.detect(job, collected)

                run.status = detected.severity
                run.severity = detected.severity
                run.error_log = collected.error if not collected.ok else None
                run.result_payload = {
                    "collect": {
                        "ok": collected.ok,
                        "status_code": collected.status_code,
                        "latency_ms": collected.latency_ms,
                        "payload": collected.payload,
                        "error": collected.error,
                    },
                    "detect": {
                        "severity": detected.severity,
                        "reason": detected.reason,
                        "should_alert": detected.should_alert,
                        "evidence": detected.evidence,
                    },
                }

                if detected.should_alert:
                    await self._create_alert(job=job, run=run, detected=detected)

                job.last_status = detected.severity
                job.last_error = None
                job.consecutive_failures = 0

            except Exception as exc:
                await self._mark_failed(job=job, run=run, error=str(exc), now=started)

        finished = datetime.utcnow()
        run.finished_at = finished
        run.latency_ms = int((finished - started).total_seconds() * 1000)
        job.last_run_at = finished

        committed = False
        if reschedule:
            if not job.is_active:
                job.next_run_at = None
            elif run.status != "failed":
                job.next_run_at = self._compute_next_run_from_job(job, finished)
            committed = await self._replace_pending_aes_task(job)

        if not committed:
            await self.db.commit()

        await self.db.refresh(run)
        return run

    async def _mark_failed(self, *, job: MonitorJob, run: MonitorJobRun, error: str, now: datetime) -> None:
        run.status = "failed"
        run.severity = "critical"
        run.error_log = error
        run.result_payload = {"error": error}

        job.last_status = "failed"
        job.last_error = error
        job.consecutive_failures = (job.consecutive_failures or 0) + 1

        if job.is_active:
            if job.consecutive_failures <= job.max_retries:
                delay = job.retry_backoff_seconds * (2 ** (job.consecutive_failures - 1))
                job.next_run_at = now + timedelta(seconds=delay)
            else:
                job.next_run_at = self._compute_next_run_from_job(job, now)
        else:
            job.next_run_at = None

        detection = DetectionResult(
            severity="critical",
            should_alert=True,
            reason=f"execution_error:{error}",
            dedupe_key=f"execution_error:{job.id}",
            evidence={"error": error},
        )
        await self._create_alert(job=job, run=run, detected=detection)

    async def _create_alert(self, *, job: MonitorJob, run: MonitorJobRun, detected: DetectionResult) -> MonitorAlert:
        now = datetime.utcnow()
        dedupe_key = detected.dedupe_key

        suppressed = False
        if job.cooldown_seconds > 0 and dedupe_key:
            stmt = (
                select(MonitorAlert)
                .filter(
                    MonitorAlert.monitor_job_id == job.id,
                    MonitorAlert.dedupe_key == dedupe_key,
                )
                .order_by(desc(MonitorAlert.triggered_at))
                .limit(1)
            )
            result = await self.db.execute(stmt)
            last_alert = result.scalars().first()
            if last_alert and last_alert.triggered_at:
                cooldown_until = last_alert.triggered_at + timedelta(seconds=job.cooldown_seconds)
                suppressed = now < cooldown_until

        alert = MonitorAlert(
            id=str(uuid.uuid4()),
            monitor_job_id=job.id,
            monitor_job_run_id=run.id,
            user_id=job.user_id,
            severity=detected.severity,
            reason=detected.reason,
            dedupe_key=dedupe_key,
            triggered_at=now,
            notification_status="suppressed" if suppressed else "pending",
            metadata_payload={
                "evidence": detected.evidence,
            },
        )
        self.db.add(alert)

        if suppressed:
            return alert

        channel = (job.notification_config or {}).get("channel", "in_app")
        title = f"[Monitor:{detected.severity.upper()}] {job.name}"
        content = f"{detected.reason}"

        try:
            notifier = get_notifier(channel, self.db)
            notification = await notifier.notify(
                user_id=job.user_id,
                title=title,
                content=content,
                link=f"/monitor/jobs/{job.id}",
            )
            alert.notification_status = "sent" if notification.sent else "failed"
            alert.sent_at = notification.sent_at
            alert.metadata_payload = {
                **(alert.metadata_payload or {}),
                "channel": notification.channel,
                "detail": notification.detail,
            }
        except Exception as exc:
            alert.notification_status = "failed"
            alert.metadata_payload = {
                **(alert.metadata_payload or {}),
                "notify_error": str(exc),
            }

        await self._enqueue_agent_delivery(job=job, alert=alert, detected=detected)

        return alert

    async def test_job_once(self, user_id: str, monitor_job_id: str) -> MonitorJobRun:
        return await self.execute_monitor_check(
            user_id=user_id,
            monitor_job_id=monitor_job_id,
            monitor_run_id=None,
            reschedule=False,
        )

    async def _replace_pending_aes_task(self, job: MonitorJob) -> bool:
        await self._delete_pending_aes_tasks(job.user_id, job.id)

        if not job.is_active or not job.next_run_at:
            return False

        scheduler = AESSchedulerService(self.db)
        await scheduler.create_task(
            user_id=job.user_id,
            task_type="MONITOR_CHECK",
            scheduled_at=job.next_run_at,
            project_id=None,
            payload={"monitor_job_id": job.id},
            recurring_rule=None,
        )
        return True

    async def _delete_pending_aes_tasks(self, user_id: str, monitor_job_id: str) -> None:
        stmt = select(ScheduledTask).filter(
            ScheduledTask.user_id == user_id,
            ScheduledTask.task_type == "MONITOR_CHECK",
            ScheduledTask.status == ScheduledTaskStatus.PENDING,
        )
        result = await self.db.execute(stmt)
        tasks = result.scalars().all()

        deleted = False
        for task in tasks:
            if (task.payload or {}).get("monitor_job_id") == monitor_job_id:
                await self.db.delete(task)
                deleted = True

        if deleted:
            await self.db.flush()

    async def _enqueue_agent_delivery(
        self,
        *,
        job: MonitorJob,
        alert: MonitorAlert,
        detected: DetectionResult,
    ) -> None:
        notification_cfg = job.notification_config or {}
        cfg = notification_cfg.get("agent_delivery") or {}
        if not cfg and notification_cfg.get("project_id"):
            cfg = {
                "enabled": True,
                "project_id": notification_cfg.get("project_id"),
                "session_id": notification_cfg.get("session_id"),
                "min_severity": notification_cfg.get("min_severity", "warn"),
            }
        enabled = bool(cfg.get("enabled", False))
        project_id = cfg.get("project_id")
        if not enabled or not project_id:
            return

        min_severity = str(cfg.get("min_severity", "warn")).lower()
        severity_rank = {"normal": 0, "warn": 1, "critical": 2, "failed": 2}
        current_rank = severity_rank.get((detected.severity or "normal").lower(), 0)
        threshold_rank = severity_rank.get(min_severity, 1)
        if current_rank < threshold_rank:
            return

        session_id = cfg.get("session_id")
        message = (
            "[MONITOR ALERT]\n"
            f"- job_id: {job.id}\n"
            f"- job_name: {job.name}\n"
            f"- severity: {detected.severity}\n"
            f"- reason: {detected.reason}\n"
            f"- alert_id: {alert.id}\n"
            "Please inspect /api/monitor/jobs/{job_id}/runs and /api/monitor/alerts for details."
        ).replace("{job_id}", job.id)

        payload: dict[str, Any] = {
            "message": message,
            "project_id": project_id,
            "monitor_job_id": job.id,
            "monitor_alert_id": alert.id,
        }
        if session_id:
            payload["session_id"] = session_id

        scheduler = AESSchedulerService(self.db)
        await scheduler.create_task(
            user_id=job.user_id,
            task_type="POST_MESSAGE",
            scheduled_at=datetime.utcnow(),
            project_id=project_id,
            payload=payload,
            recurring_rule=None,
        )

    @staticmethod
    def _is_within_valid_window(job: MonitorJob, now: datetime) -> bool:
        if job.valid_from and now < job.valid_from:
            return False
        if job.valid_until and now > job.valid_until:
            return False
        return True

    def _compute_next_run_from_job(self, job: MonitorJob, after: datetime) -> Optional[datetime]:
        return self._compute_next_run(
            schedule_cron=job.schedule_cron,
            timezone=job.timezone,
            valid_from=job.valid_from,
            valid_until=job.valid_until,
            after=after,
        )

    def _compute_next_run(
        self,
        schedule_cron: str,
        timezone: str,
        valid_from: Optional[datetime],
        valid_until: Optional[datetime],
        after: datetime,
    ) -> Optional[datetime]:
        anchor = after
        if valid_from and anchor < valid_from:
            anchor = valid_from

        if valid_until and anchor > valid_until:
            return None

        candidate = next_run_at_utc(schedule_cron, timezone, after_utc=anchor)
        if valid_until and candidate > valid_until:
            return None

        return candidate

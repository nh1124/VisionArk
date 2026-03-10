"""Codex CLI — LRJ handler for "cli.run_shell".

Registered into lrj_registry via @lrj_registry.register, exactly like
LINE's task/reply handlers. Imported by codex/__init__.py so the decorator
fires when the codex package is first loaded by the integration loader.

The executor calls: handler_cls().run(job, svc, db)
where svc = LongRunningJobService (passed in — no import needed here).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from va_sdk import lrj_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from shared.database import LongRunningJob
    from integrations._internal_services import LongRunningJobService as _Svc

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {"succeeded", "failed", "rejected"}
_POLL_INTERVAL_SEC = 2.0
_MAX_POLL_SEC = 3600
_PROGRESS_MIN_INTERVAL_SEC = 8.0
_DEFAULT_STALL_TIMEOUT_SEC = 420


@lrj_registry.register("cli.run_shell")
class CliShellHandler:
    """Polls a RunExecution until terminal, then completes or fails the LRJ."""

    async def run(
        self,
        job: "LongRunningJob",
        svc: "type[_Svc]",
        db: "AsyncSession",
    ) -> None:
        payload = job.input_payload or {}
        execution_id: str | None = payload.get("execution_id")
        stall_timeout_sec = int(payload.get("stall_timeout_sec") or _DEFAULT_STALL_TIMEOUT_SEC)

        if not execution_id:
            await svc.fail_job(db, job.id, "missing_execution_id",
                               "No execution_id in job input_payload.")
            return

        from sqlalchemy import select
        from shared.database import RunExecution

        deadline = time.monotonic() + _MAX_POLL_SEC
        exc = None
        last_progress_emit = 0.0
        last_progress_message: str = ""
        last_partial: str = ""
        partial_unchanged_since = time.monotonic()

        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL_SEC)

            res = await db.execute(
                select(RunExecution)
                .where(RunExecution.id == execution_id)
                .execution_options(populate_existing=True)  # bypass identity map cache
            )
            exc = res.scalars().first()

            if exc is None:
                await svc.fail_job(db, job.id, "not_found",
                                   f"RunExecution '{execution_id}' not found.")
                return

            if exc.status == "waiting_approval":
                await svc.update_progress(db, job.id, {
                    "pct": 30, "message": "Waiting for user approval in Run Center.",
                })
                deadline = max(deadline, time.monotonic() + 300)
                continue

            if exc.status in _TERMINAL_STATES:
                break

            # Show partial stdout so the agent can inspect what codex is outputting
            partial = (exc.partial_stdout or "").strip()
            now = time.monotonic()
            if partial == last_partial:
                pass
            else:
                last_partial = partial
                partial_unchanged_since = now

            if exc.status == "running" and (now - partial_unchanged_since) >= stall_timeout_sec:
                from integrations._internal_services import RunService
                reason = (
                    "Execution appears stalled: no output change for "
                    f"{stall_timeout_sec}s (status=running)."
                )
                logger.warning(
                    "cli.run_shell stalled job=%s exec=%s stall_timeout_sec=%s",
                    job.id, execution_id, stall_timeout_sec,
                )
                try:
                    await RunService.update_execution_status(
                        db=db,
                        exec_id=execution_id,
                        user_id=job.user_id,
                        status="failed",
                        error_log=reason,
                    )
                except Exception:
                    logger.exception(
                        "failed to mark stalled execution failed job=%s exec=%s",
                        job.id, execution_id,
                    )
                await svc.fail_job(db, job.id, "stalled", reason)
                return

            progress_message = partial[-3000:] if partial else f"Execution status: {exc.status}"
            should_emit = (
                progress_message != last_progress_message
                or (now - last_progress_emit) >= _PROGRESS_MIN_INTERVAL_SEC
            )
            if should_emit:
                await svc.update_progress(db, job.id, {
                    "pct": 10,
                    "message": progress_message,
                    "has_output": bool(partial),
                    "execution_status": exc.status,
                    "execution_id": execution_id,
                })
                last_progress_emit = now
                last_progress_message = progress_message

        else:
            await svc.fail_job(db, job.id, "timeout",
                               f"RunExecution '{execution_id}' timed out after {_MAX_POLL_SEC}s.")
            return

        if exc.status == "rejected":
            await svc.fail_job(db, job.id, "rejected",
                               "Execution was rejected by the user.")
            return

        if exc.status == "failed":
            await svc.fail_job(db, job.id, "execution_failed",
                               exc.error_log or "Execution failed without details.")
            return

        # succeeded
        raw: dict = exc.result or {}
        stdout: str = raw.get("stdout", "")
        stderr: str = raw.get("stderr", "")
        exit_code: int = raw.get("exit_code", 0)

        if exit_code != 0:
            await svc.fail_job(
                db, job.id, "nonzero_exit",
                f"Command exited {exit_code}: {(stderr or stdout).strip()[:500]}",
            )
        else:
            await svc.complete_job(db, job.id, {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_id": execution_id,
            })

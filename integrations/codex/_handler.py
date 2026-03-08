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

        if not execution_id:
            await svc.fail_job(db, job.id, "missing_execution_id",
                               "No execution_id in job input_payload.")
            return

        from sqlalchemy import select
        from shared.database import RunExecution

        deadline = time.monotonic() + _MAX_POLL_SEC
        exc = None

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
            await svc.update_progress(db, job.id, {
                "pct": 10,
                "message": partial[-3000:] if partial else f"Execution status: {exc.status}",
                "has_output": bool(partial),
            })

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

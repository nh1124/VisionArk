"""DeepResearchJobHandler — resumes a Gemini deep research interaction in background."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from domains.long_running.executor.base import BaseLRJHandler, register_lrj_handler

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from shared.database import LongRunningJob
    from domains.long_running.services.job_service import LongRunningJobService as _Svc

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SEC = 10
_MAX_POLL_SEC      = 3600   # 1 hour absolute ceiling per handler run


@register_lrj_handler("research.gemini.deep")
class DeepResearchJobHandler(BaseLRJHandler):
    """Resumes a Gemini Interactions API polling session for a long-running deep research job."""

    async def run(
        self,
        job: "LongRunningJob",
        svc: "type[_Svc]",
        db: "AsyncSession",
    ) -> None:
        interaction_id = job.external_ref
        if not interaction_id:
            await svc.fail_job(db, job.id, "missing_interaction_id", "No external_ref set on job.")
            return

        # Retrieve the user's Gemini API key from DB
        api_key = await self._get_api_key(db, job.user_id)
        if not api_key:
            await svc.fail_job(
                db, job.id, "no_api_key",
                f"No Gemini API key configured for user {job.user_id}.",
            )
            return

        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except ImportError as exc:
            await svc.fail_job(db, job.id, "import_error", str(exc))
            return

        model = job.model or "deep-research-pro-preview-12-2025"
        already_elapsed = 0.0
        if job.started_at:
            from datetime import datetime
            now = datetime.utcnow()
            already_elapsed = (now - job.started_at.replace(tzinfo=None)).total_seconds()

        remaining = max(0.0, _MAX_POLL_SEC - already_elapsed)
        elapsed   = 0.0

        logger.info(
            "[DeepResearchHandler] resuming job=%s interaction=%s remaining=%.0fs",
            job.id, interaction_id, remaining,
        )

        while elapsed < remaining:
            await asyncio.sleep(_POLL_INTERVAL_SEC)
            elapsed += _POLL_INTERVAL_SEC

            try:
                interaction = await asyncio.to_thread(client.interactions.get, interaction_id)
            except Exception as exc:
                logger.warning("[DeepResearchHandler] poll error job=%s: %s", job.id, exc)
                continue

            status = interaction.status
            logger.debug(
                "[DeepResearchHandler] job=%s interaction=%s status=%s elapsed=%.0fs",
                job.id, interaction_id, status, elapsed,
            )

            if status == "completed":
                outputs = getattr(interaction, "outputs", []) or []
                text = outputs[-1].text if outputs else ""
                if not text:
                    await svc.fail_job(
                        db, job.id, "empty_result",
                        f"Gemini ({model}) completed but returned no text.",
                    )
                    return

                # Persist result to file via shared utility
                from domains.long_running.utils import save_result_to_file
                result_path = await save_result_to_file(
                    job.user_id, job.id, text,
                    sub_dir="research",
                    filename=job.result_path,
                )
                await svc.complete_job(
                    db, job.id,
                    result_payload={"text": text[:512]},
                    result_path=result_path,
                )
                logger.info("[DeepResearchHandler] job=%s completed", job.id)
                return

            elif status == "failed":
                error = getattr(interaction, "error", "Unknown error")
                await svc.fail_job(db, job.id, "provider_error", str(error))
                logger.warning("[DeepResearchHandler] job=%s provider failed: %s", job.id, error)
                return

        # Absolute ceiling hit
        await svc.fail_job(
            db, job.id, "handler_timeout",
            f"Research did not complete within {_MAX_POLL_SEC}s (interaction={interaction_id}).",
        )
        logger.warning("[DeepResearchHandler] job=%s timed out after %.0fs", job.id, elapsed)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_api_key(db: "AsyncSession", user_id: str) -> str | None:
        from sqlalchemy import select
        from shared.database import UserSettings
        res = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        settings = res.scalars().first()
        return settings.gemini_api_key if settings else None

"""ResearchInlineHandler — background re-run of a deep research job.

Triggered when the sync tool call (any non-Gemini-deep provider) times out
with async_on_timeout=True.  Re-executes the full provider query from the
job's input_payload and saves the result to the user's artifacts directory.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domains.long_running.executor.base import BaseLRJHandler, register_lrj_handler

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from shared.database import LongRunningJob
    from domains.long_running.services.job_service import LongRunningJobService as _Svc

logger = logging.getLogger(__name__)


@register_lrj_handler("research.inline")
class ResearchInlineHandler(BaseLRJHandler):
    """Background re-run handler for Gemini-fast, OpenAI, and Anthropic research jobs."""

    async def run(
        self,
        job: "LongRunningJob",
        svc: "type[_Svc]",
        db: "AsyncSession",
    ) -> None:
        from domains.long_running.providers import (
            do_gemini_fast, do_openai, do_anthropic,
            get_api_key_for_provider,
        )
        from domains.long_running.utils import save_result_to_file

        query    = (job.input_payload or {}).get("query", "")
        model    = job.model or (job.input_payload or {}).get("model", "")
        provider = job.provider or ""

        if not query or not model or not provider:
            await svc.fail_job(
                db, job.id, "missing_input",
                f"Job missing required fields — "
                f"query={bool(query)} model={bool(model)} provider={bool(provider)}",
            )
            return

        api_key = await get_api_key_for_provider(db, job.user_id, provider)
        if not api_key:
            await svc.fail_job(
                db, job.id, "no_api_key",
                f"No API key for provider '{provider}' (user={job.user_id})",
            )
            return

        try:
            if provider == "gemini":
                text, _ = await do_gemini_fast(query, model, api_key)
            elif provider == "openai":
                text, _ = await do_openai(query, model, api_key)
            elif provider == "anthropic":
                text, _ = await do_anthropic(query, model, api_key)
            else:
                await svc.fail_job(
                    db, job.id, "unknown_provider",
                    f"Unsupported provider: '{provider}'",
                )
                return
        except RuntimeError as exc:
            await svc.fail_job(db, job.id, "provider_error", str(exc))
            return

        if not text:
            await svc.fail_job(db, job.id, "empty_result", "Provider returned no content.")
            return

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
        logger.info(
            "[ResearchInlineHandler] job=%s completed provider=%s model=%s",
            job.id, provider, model,
        )

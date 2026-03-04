"""Shared utilities for long-running job result persistence."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def save_result_to_file(
    user_id: str,
    job_id: str,
    text: str,
    *,
    sub_dir: str = "research",
    filename: str | None = None,
    extension: str = ".md",
) -> str:
    """Save text to artifacts/{sub_dir}/ under the user's data directory.

    Returns the absolute path of the saved file.
    Can be reused by any long-running tool (reports, code generation, etc.).
    """
    try:
        from shared.paths import get_user_root_dir
        base = get_user_root_dir(user_id) / "artifacts" / sub_dir
    except Exception:
        base = Path(f"data/users/{user_id}/artifacts/{sub_dir}")

    base.mkdir(parents=True, exist_ok=True)

    if filename:
        fname = Path(filename).name   # prevent directory traversal
    else:
        fname = f"{job_id}{extension}"

    path = base / fname
    await asyncio.to_thread(path.write_text, text, "utf-8")
    logger.info("[LRJ] saved result to %s", path)
    return str(path)

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

import requests

from domains.monitoring.collectors.base import BaseCollector
from domains.monitoring.models import CollectionResult
from shared.database import MonitorJob


class URLCollector(BaseCollector):
    async def collect(self, job: MonitorJob) -> CollectionResult:
        cfg: Dict[str, Any] = job.source_config or {}
        url = cfg.get("url")
        method = str(cfg.get("method", "GET")).upper()
        timeout = int(cfg.get("timeout_seconds", 10))
        headers = cfg.get("headers") or {}

        if not url:
            return CollectionResult(ok=False, error="source_config.url is required")

        def _request() -> CollectionResult:
            start = time.perf_counter()
            try:
                resp = requests.request(
                    method=method,
                    url=url,
                    timeout=timeout,
                    headers=headers,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                body = resp.text or ""
                sample_len = int(cfg.get("body_sample_chars", 2000))
                payload = {
                    "url": url,
                    "method": method,
                    "body": body[:sample_len],
                    "content_type": resp.headers.get("content-type"),
                    "content_length": len(body),
                }
                return CollectionResult(
                    ok=True,
                    status_code=resp.status_code,
                    latency_ms=latency_ms,
                    payload=payload,
                )
            except Exception as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return CollectionResult(
                    ok=False,
                    status_code=None,
                    latency_ms=latency_ms,
                    error=str(exc),
                    payload={"url": url, "method": method},
                )

        return await asyncio.to_thread(_request)

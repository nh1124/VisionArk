from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict
from urllib.parse import urlparse

import requests

from domains.monitoring.collectors.base import BaseCollector
from domains.monitoring.models import CollectionResult
from shared.database import MonitorJob


def _resolve_runtime_url(raw_url: str) -> str:
    """Rewrite localhost targets when running inside Docker."""
    if not raw_url or not os.path.exists("/.dockerenv"):
        return raw_url

    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        return raw_url

    netloc = parsed.netloc
    if not netloc:
        return raw_url

    if "@" in netloc:
        auth, host_port = netloc.rsplit("@", 1)
        auth_prefix = f"{auth}@"
    else:
        host_port = netloc
        auth_prefix = ""

    if host_port.startswith("["):
        close_idx = host_port.find("]")
        if close_idx == -1:
            return raw_url
        suffix = host_port[close_idx + 1 :]
    else:
        colon_idx = host_port.find(":")
        suffix = host_port[colon_idx:] if colon_idx >= 0 else ""

    rewritten_netloc = f"{auth_prefix}host.docker.internal{suffix}"
    return parsed._replace(netloc=rewritten_netloc).geturl()


class URLCollector(BaseCollector):
    async def collect(self, job: MonitorJob) -> CollectionResult:
        cfg: Dict[str, Any] = job.source_config or {}
        url = cfg.get("url")
        resolved_url = _resolve_runtime_url(url)
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
                    url=resolved_url,
                    timeout=timeout,
                    headers=headers,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                body = resp.text or ""
                sample_len = int(cfg.get("body_sample_chars", 2000))
                payload = {
                    "url": url,
                    "resolved_url": resolved_url,
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
                    payload={"url": url, "resolved_url": resolved_url, "method": method},
                )

        return await asyncio.to_thread(_request)

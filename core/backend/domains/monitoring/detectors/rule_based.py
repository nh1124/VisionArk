from __future__ import annotations

from typing import Any, Dict

from domains.monitoring.detectors.base import BaseDetector
from domains.monitoring.models import CollectionResult, DetectionResult
from shared.database import MonitorJob


class RuleBasedDetector(BaseDetector):
    def detect(self, job: MonitorJob, collected: CollectionResult) -> DetectionResult:
        cfg: Dict[str, Any] = job.detector_config or {}
        expected_status = int(cfg.get("expected_status", 200))
        max_latency_ms = cfg.get("max_latency_ms")
        contains_any = cfg.get("contains_any") or []
        not_contains_any = cfg.get("not_contains_any") or []

        evidence: Dict[str, Any] = {
            "status_code": collected.status_code,
            "latency_ms": collected.latency_ms,
            "source": collected.payload.get("url") if collected.payload else None,
        }

        if not collected.ok:
            reason = f"collector_error:{collected.error or 'unknown'}"
            return DetectionResult(
                severity="critical",
                should_alert=True,
                reason=reason,
                dedupe_key=f"collector_error:{job.id}",
                evidence=evidence,
            )

        if collected.status_code is None or collected.status_code != expected_status:
            reason = f"status_mismatch:{collected.status_code}!={expected_status}"
            return DetectionResult(
                severity="critical",
                should_alert=True,
                reason=reason,
                dedupe_key=f"status:{job.id}:{expected_status}",
                evidence=evidence,
            )

        if max_latency_ms is not None and collected.latency_ms is not None:
            if collected.latency_ms > int(max_latency_ms):
                reason = f"latency_high:{collected.latency_ms}>{max_latency_ms}"
                return DetectionResult(
                    severity="warn",
                    should_alert=True,
                    reason=reason,
                    dedupe_key=f"latency:{job.id}:{max_latency_ms}",
                    evidence=evidence,
                )

        body = str((collected.payload or {}).get("body") or "")

        if contains_any:
            if not any(term in body for term in contains_any):
                reason = "contains_any_not_found"
                return DetectionResult(
                    severity="warn",
                    should_alert=True,
                    reason=reason,
                    dedupe_key=f"contains_any:{job.id}",
                    evidence={**evidence, "contains_any": contains_any},
                )

        if not_contains_any:
            hit = next((term for term in not_contains_any if term in body), None)
            if hit:
                reason = f"forbidden_keyword:{hit}"
                return DetectionResult(
                    severity="critical",
                    should_alert=True,
                    reason=reason,
                    dedupe_key=f"forbidden:{job.id}:{hit}",
                    evidence={**evidence, "hit": hit},
                )

        return DetectionResult(
            severity="normal",
            should_alert=False,
            reason="normal",
            dedupe_key=f"normal:{job.id}",
            evidence=evidence,
        )

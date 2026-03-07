from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class CollectionResult:
    ok: bool
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class DetectionResult:
    severity: str  # normal | warn | critical
    should_alert: bool
    reason: str
    dedupe_key: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationResult:
    sent: bool
    channel: str
    detail: str
    sent_at: Optional[datetime] = None

from __future__ import annotations

from abc import ABC, abstractmethod

from domains.monitoring.models import CollectionResult, DetectionResult
from shared.database import MonitorJob


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, job: MonitorJob, collected: CollectionResult) -> DetectionResult:
        raise NotImplementedError


def get_detector(detector_type: str) -> BaseDetector:
    normalized = (detector_type or "").upper()
    if normalized in {"RULE_BASED", "THRESHOLD", "RULE"}:
        from domains.monitoring.detectors.rule_based import RuleBasedDetector

        return RuleBasedDetector()
    raise ValueError(f"Unsupported detector_type: {detector_type}")

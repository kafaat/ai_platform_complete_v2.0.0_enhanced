"""RS-6 signal-anomaly detection over canonical baseline comparisons.

This module detects *signals*, not agronomic causes. It consumes baseline
comparisons produced by RS-5 and never reads raster pixels or creates
prescriptions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DetectedSignal:
    anomaly_ref: str
    detection_run_ref: str
    primary_observation_ref: str
    baseline_run_ref: str
    signal_type: str
    severity: str
    confidence: Decimal
    deviation: Decimal
    deviation_percent: Decimal | None
    verification_requirement: str
    verification_deadline: datetime | None
    reason_codes: tuple[str, ...]
    detected_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_ref": self.anomaly_ref,
            "detection_run_ref": self.detection_run_ref,
            "primary_observation_ref": self.primary_observation_ref,
            "baseline_run_ref": self.baseline_run_ref,
            "signal_type": self.signal_type,
            "severity": self.severity,
            "confidence": str(self.confidence),
            "confidence_method": "minimum_measured_input_quality_v2",
            "confidence_is_probability": False,
            "deviation": str(self.deviation),
            "deviation_percent": (
                str(self.deviation_percent) if self.deviation_percent is not None else None
            ),
            "verification_requirement": self.verification_requirement,
            "verification_deadline": (
                self.verification_deadline.isoformat()
                if self.verification_deadline is not None
                else None
            ),
            "reason_codes": list(self.reason_codes),
            "detected_at": self.detected_at.isoformat(),
        }


def _ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    return f"urn:sahool:{prefix}:{prefix.split('-')[-1]}_{digest}"


def _severity(percent: Decimal | None, absolute: Decimal) -> str:
    magnitude = abs(percent) if percent is not None else abs(absolute) * Decimal("100")
    if magnitude >= Decimal("30"):
        return "critical"
    if magnitude >= Decimal("20"):
        return "high"
    if magnitude >= Decimal("12"):
        return "medium"
    if magnitude >= Decimal("7"):
        return "low"
    return "info"


def _confidence(baseline_confidence: Decimal, severity: str, sample_size: int) -> Decimal:
    # An input-quality score, not a calibrated probability of agronomic harm.
    # Severity and sample count cannot create evidence about correctness.
    return max(Decimal("0"), min(Decimal("1"), baseline_confidence))


def detect_signals(
    *,
    field_id: str,
    indicator: str,
    comparisons: list[dict[str, Any]],
    min_deviation_percent: Decimal = Decimal("7"),
    now: datetime | None = None,
) -> list[DetectedSignal]:
    """Return deterministic signal anomalies for material deviations only.

    Multiple baseline comparisons for the same observation are deduplicated by
    preferring matched stage, then previous valid, then historical median. No suspected cause is emitted.
    """
    now = now or datetime.now(UTC)
    candidates: list[DetectedSignal] = []
    # Select the scientific reference before applying the alert threshold. A quiet
    # matched stage must not fall back to a large normal seasonal growth signal.
    order = {"same_phenological_stage": 0, "previous_valid": 1, "historical_robust_median": 2}
    if comparisons:
        best = min(order.get(c.get("baseline_type"), 3) for c in comparisons)
        comparisons = [c for c in comparisons if order.get(c.get("baseline_type"), 3) == best]
    for item in comparisons:
        try:
            deviation = Decimal(str(item["deviation"]))
            pct_raw = item.get("deviation_percent")
            deviation_percent = Decimal(str(pct_raw)) if pct_raw is not None else None
            baseline_confidence = Decimal(str(item.get("expected_confidence")))
            sample_size = int(item.get("sample_size") or 0)
            primary_ref = str(item["primary_observation_ref"])
            baseline_run_ref = str(item["baseline_run_ref"])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if deviation_percent is not None and not deviation_percent.is_finite():
            continue
        if deviation_percent is not None and abs(deviation_percent) < min_deviation_percent:
            continue
        if not deviation.is_finite() or not baseline_confidence.is_finite():
            continue
        if deviation_percent is None or not deviation_percent.is_finite():
            continue
        severity = _severity(deviation_percent, deviation)
        direction = "decline" if deviation < 0 else "increase"
        signal_type = f"{indicator}_{direction}"
        requirement = "required" if severity in {"critical", "high", "medium"} else "recommended"
        deadline = now + timedelta(hours=24 if severity in {"critical", "high"} else 72)
        detection_run_ref = _ref(
            "processing-run",
            field_id,
            indicator,
            primary_ref,
            baseline_run_ref,
            "signal-detector-v2",
        )
        anomaly_ref = _ref(
            "anomaly", field_id, indicator, primary_ref, baseline_run_ref, str(deviation)
        )
        candidates.append(
            DetectedSignal(
                anomaly_ref=anomaly_ref,
                detection_run_ref=detection_run_ref,
                primary_observation_ref=primary_ref,
                baseline_run_ref=baseline_run_ref,
                signal_type=signal_type,
                severity=severity,
                confidence=_confidence(baseline_confidence, severity, sample_size),
                deviation=deviation,
                deviation_percent=deviation_percent,
                verification_requirement=requirement,
                verification_deadline=deadline,
                reason_codes=(
                    "canonical_observation_baseline",
                    f"baseline:{item.get('baseline_type', 'unknown')}",
                    f"direction:{direction}",
                ),
                detected_at=now,
            )
        )
    if not candidates:
        return []
    # Within the selected reference type, retain the strongest signal.
    strongest = max(
        candidates,
        key=lambda c: (
            abs(c.deviation_percent)
            if c.deviation_percent is not None
            else abs(c.deviation) * Decimal("100")
        ),
    )
    return [strongest]

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
    severity_bonus = {
        "critical": Decimal("0.08"),
        "high": Decimal("0.06"),
        "medium": Decimal("0.04"),
        "low": Decimal("0.02"),
        "info": Decimal("0.00"),
    }[severity]
    sample_bonus = min(Decimal("0.08"), Decimal(sample_size) * Decimal("0.01"))
    return min(Decimal("0.99"), baseline_confidence + severity_bonus + sample_bonus)


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
    retaining the strongest absolute deviation. No suspected cause is emitted.
    """
    now = now or datetime.now(UTC)
    candidates: list[DetectedSignal] = []
    for item in comparisons:
        try:
            deviation = Decimal(str(item["deviation"]))
            pct_raw = item.get("deviation_percent")
            deviation_percent = Decimal(str(pct_raw)) if pct_raw is not None else None
            baseline_confidence = Decimal(str(item.get("expected_confidence", "0.5")))
            sample_size = int(item.get("sample_size") or 0)
            primary_ref = str(item["primary_observation_ref"])
            baseline_run_ref = str(item["baseline_run_ref"])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if deviation_percent is not None and abs(deviation_percent) < min_deviation_percent:
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
            "signal-detector-v1",
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
    # One signal per primary observation/indicator. Preserve the strongest evidence.
    strongest = max(
        candidates,
        key=lambda c: (
            abs(c.deviation_percent)
            if c.deviation_percent is not None
            else abs(c.deviation) * Decimal("100")
        ),
    )
    return [strongest]

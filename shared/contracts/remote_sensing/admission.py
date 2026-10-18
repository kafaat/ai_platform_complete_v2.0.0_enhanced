"""Measured admission policy for temporal inference, separate from display."""

from decimal import Decimal, InvalidOperation
from typing import Any

POLICY_VERSION = "2.0.0"
MIN_VALID_RATIO = Decimal("0.70")
MIN_COVERAGE_RATIO = Decimal("0.70")
MAX_CLOUD_RATIO = Decimal("0.35")


def finite_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def quality_reasons(quality: dict) -> tuple[str, ...]:
    reasons = []
    for key, threshold, minimum in (
        ("valid_pixel_ratio", MIN_VALID_RATIO, True),
        ("field_coverage_ratio", MIN_COVERAGE_RATIO, True),
        ("field_cloud_ratio", MAX_CLOUD_RATIO, False),
    ):
        value = finite_decimal(quality.get(key))
        if value is None or not Decimal(0) <= value <= Decimal(1):
            reasons.append(f"{key}_unavailable")
        elif (minimum and value < threshold) or (not minimum and value > threshold):
            reasons.append(f"{key}_outside_policy")
    return tuple(reasons)


def admissible(quality: dict) -> bool:
    return (
        quality.get("gate_status") == "passed"
        and (quality.get("policy") or {}).get("use_case") == "anomaly_detection"
        and quality.get("indicator_in_range") is not False
        and not quality_reasons(quality)
    )

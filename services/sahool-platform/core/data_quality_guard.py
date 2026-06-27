"""Data quality checks for Canonical Field State inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class QualityIssue:
    field: str
    severity: Severity
    message_ar: str


@dataclass(frozen=True)
class QualityReport:
    issues: list[QualityIssue]

    @property
    def blocks_decision(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def score(self) -> int:
        score = 100 - sum(
            30 if i.severity == "error" else 10 if i.severity == "warning" else 2
            for i in self.issues
        )
        return max(0, score)


def validate_agronomic_ranges(values: dict[str, Any]) -> QualityReport:
    issues: list[QualityIssue] = []
    ranges = {
        "soil_ph": (3.0, 10.5),
        "soil_ec_ds_m": (0.0, 30.0),
        "water_ec_ds_m": (0.0, 20.0),
        "ndvi": (-1.0, 1.0),
        "et0_mm": (0.0, 20.0),
        "wind_speed_m_s": (0.0, 60.0),
    }
    for key, (lo, hi) in ranges.items():
        if key not in values or values[key] is None:
            continue
        try:
            number = float(values[key])
        except (TypeError, ValueError):
            issues.append(QualityIssue(key, "error", f"{key} ليست قيمة رقمية صالحة"))
            continue
        if number < lo or number > hi:
            issues.append(QualityIssue(key, "error", f"{key} خارج النطاق الزراعي المقبول"))
    if values.get("soil_ec_ds_m") is None and values.get("salinity_index") is not None:
        issues.append(
            QualityIssue("soil_ec_ds_m", "warning", "مؤشر الملوحة قرينة ولا يغني عن تحليل EC مخبري")
        )
    return QualityReport(issues)

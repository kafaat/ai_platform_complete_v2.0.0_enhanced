"""Pure equipment fleet intelligence; no telemetry or physical-device claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

SCHEMA_VERSION = "equipment_intelligence.v1"


@dataclass(frozen=True)
class EquipmentIntelligenceState:
    schema_version: str
    total_assets: int
    service_due: int
    unavailable: int
    total_operating_hours: float
    utilization_known_assets: int
    readiness: str
    due_asset_ids: list[str]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_equipment(
    *,
    assets: list[dict[str, Any]],
    as_of: date | None = None,
    default_service_interval_hours: float = 250.0,
) -> EquipmentIntelligenceState:
    as_of = as_of or date.today()
    due, unavailable, hours, known = [], 0, 0.0, 0
    limitations: list[str] = []
    for index, asset in enumerate(assets):
        aid = str(asset.get("id") or asset.get("equipment_id") or f"asset-{index}")
        status = str(asset.get("status") or "unknown")
        if status in {"broken", "maintenance", "retired", "unavailable"}:
            unavailable += 1
        h = asset.get("operating_hours")
        try:
            hval = float(h)
        except (TypeError, ValueError):
            hval = None
        if hval is not None and hval >= 0:
            hours += hval
            known += 1
        else:
            limitations.append(f"operating_hours_missing:{aid}")
        interval = float(asset.get("service_interval_hours") or default_service_interval_hours)
        last = asset.get("last_service_hours")
        try:
            lastval = float(last)
        except (TypeError, ValueError):
            lastval = 0.0
        date_due = False
        raw_due = asset.get("next_service_date")
        if raw_due:
            try:
                date_due = datetime.fromisoformat(str(raw_due)).date() <= as_of
            except ValueError:
                limitations.append(f"invalid_next_service_date:{aid}")
        hours_due = hval is not None and hval - lastval >= interval
        if date_due or hours_due:
            due.append(aid)
    readiness = (
        "blocked"
        if unavailable == len(assets) and assets
        else "degraded"
        if unavailable or due
        else "ready"
    )
    if not assets:
        readiness = "unknown"
        limitations.append("no_equipment_assets")
    return EquipmentIntelligenceState(
        SCHEMA_VERSION,
        len(assets),
        len(due),
        unavailable,
        round(hours, 2),
        known,
        readiness,
        due,
        list(dict.fromkeys(limitations)),
    )

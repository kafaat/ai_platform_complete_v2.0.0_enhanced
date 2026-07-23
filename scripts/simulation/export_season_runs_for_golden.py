#!/usr/bin/env python3
"""Export eligible append-only season simulation runs to SIM-GOLDEN input.

The exporter is intentionally separate from ``sim_golden.py``: it selects and
normalizes evidence, while SIM-GOLDEN remains a deterministic validation gate.
Input is a JSON array produced by the documented SQL query or an object with a
``rows`` array. Tenant identifiers are pseudonymized and never exported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path


class ExportError(ValueError):
    pass


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_ts(value) -> datetime | None:
    """Parse an ISO timestamp/date to a naive-UTC datetime for safe comparison.

    Aware values are converted to UTC then made naive so aware/naive mixes never
    raise on comparison. Returns None when the value cannot be parsed (the caller
    fails closed on None — an unprovable ordering must not enter the golden set).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        text = str(value).strip().replace("Z", "+00:00")
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text[:10])
            except ValueError:
                return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _value(row: dict, *paths: str):
    for path in paths:
        current = row
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current is not None:
            return current
    return None


def export_rows(rows: list[dict], *, pseudonym_salt: str) -> dict:
    if len(pseudonym_salt) < 16:
        raise ExportError("pseudonym_salt must contain at least 16 characters")
    samples: list[dict] = []
    rejected: list[dict] = []
    for row in rows:
        reason = None
        mode = str(row.get("mode") or "")
        observed = _value(row, "observed_yield_kg_ha", "harvest.yield_kg_ha")
        predicted = _value(
            row, "predicted_yield_kg_ha", "result.yield_kg_ha", "result.estimated_yield_kg_ha"
        )
        source = _value(row, "observation_source", "harvest.observation_source")
        prediction_at = row.get("prediction_at") or row.get("created_at")
        harvest_at = _value(row, "harvest_at", "harvest.harvest_at", "harvest.harvest_date")
        if mode != "historical_hindcast":
            reason = "mode_not_historical_hindcast"
        elif source not in {"combine_weighbridge", "certified_scale", "erp_verified"}:
            reason = "unverified_harvest_source"
        elif observed is None or predicted is None:
            reason = "missing_yield"
        elif not prediction_at or not harvest_at:
            reason = "missing_timestamps"
        elif not row.get("input_digest") or not row.get("engine_version"):
            reason = "missing_reproducibility_lineage"
        else:
            # Temporal-leak guard: a hindcast prediction MUST be produced strictly
            # before the harvest is observed, else the "prediction" could encode the
            # actual outcome. Unparseable timestamps fail closed — an unprovable
            # ordering must never enter the golden set.
            prediction_ts = _parse_ts(prediction_at)
            harvest_ts = _parse_ts(harvest_at)
            if prediction_ts is None or harvest_ts is None:
                reason = "unparseable_timestamps"
            elif prediction_ts >= harvest_ts:
                reason = "temporal_leak_prediction_not_before_harvest"
        if reason:
            rejected.append({"run_id": str(row.get("run_id") or ""), "reason": reason})
            continue
        farm_key = str(row.get("farm_id") or row.get("field_id") or "")
        if not farm_key:
            rejected.append({"run_id": str(row.get("run_id") or ""), "reason": "missing_farm"})
            continue
        samples.append(
            {
                "sample_id": str(row.get("run_id")),
                "crop": str(row.get("crop") or row.get("crop_code") or "").lower(),
                "season_id": str(row.get("season_id")),
                "farm_id": _sha(f"{pseudonym_salt}:{farm_key}")[:24],
                "observed_yield_kg_ha": float(observed),
                "predicted_yield_kg_ha": float(predicted),
                "observation_source": source,
                "harvest_at": str(harvest_at),
                "prediction_at": str(prediction_at),
                "model_version": str(row.get("engine_version")),
                "input_digest": str(row.get("input_digest")).lower(),
            }
        )
    samples.sort(key=lambda item: (item["crop"], item["season_id"], item["sample_id"]))
    return {
        "schema_version": 1,
        "samples": samples,
        "export_summary": {
            "eligible": len(samples),
            "rejected": len(rejected),
            "rejections": rejected,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pseudonym-salt", required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ExportError("input must be a JSON array or an object containing rows")
    output = export_rows(rows, pseudonym_salt=args.pseudonym_salt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

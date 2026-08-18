"""Fail-closed contract for future INT-004C machinery as-applied receipts.

This module does not claim a controller transport exists.  It verifies a receipt
*after* a trusted adapter supplies one, binding it to the immutable machine artifact
and saved prescription lineage.  The result can later feed Decision outcome
verification, but this module never performs that write itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "canonical_machinery_as_applied.v1"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


@dataclass(frozen=True)
class ZoneVariance:
    zone_id: str
    expected_rate: float
    actual_rate: float
    unit: str
    variance_pct: float
    within_tolerance: bool


@dataclass(frozen=True)
class MachineryAsAppliedTruth:
    schema_version: str
    artifact_id: str
    package_sha256: str
    prescription_digest: str
    receipt_id: str
    observed_at: str
    device_id: str
    device_identity_verified: bool
    verification_state: str
    zone_variances: list[ZoneVariance]
    limitations: list[str]
    outcome_eligible: bool
    as_applied_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "zone_variances": [asdict(z) for z in self.zone_variances],
        }


def verify_machinery_as_applied(
    *,
    artifact_id: str,
    expected_package_sha256: str,
    expected_prescription_digest: str,
    expected_zones: list[dict[str, Any]],
    receipt: dict[str, Any],
    allowed_rate_variance_pct: float,
) -> MachineryAsAppliedTruth:
    """Verify one terminal machine receipt against the immutable exported task.

    ``allowed_rate_variance_pct`` is passed from the approved operation/controller
    contract.  This verifier deliberately does not invent a universal agronomic tolerance.
    """
    if not all(
        _nonempty(v) for v in (artifact_id, expected_package_sha256, expected_prescription_digest)
    ):
        raise ValueError("artifact identity and digests are required")
    if allowed_rate_variance_pct < 0:
        raise ValueError("allowed_rate_variance_pct must be non-negative")
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be an object")

    required = ("receipt_id", "observed_at", "device_id", "package_sha256", "prescription_digest")
    missing = [k for k in required if not _nonempty(receipt.get(k))]
    if missing:
        raise ValueError(f"receipt missing required fields: {', '.join(missing)}")

    # Parse timestamp so an opaque/non-temporal receipt cannot become evidence.
    try:
        datetime.fromisoformat(str(receipt["observed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("receipt observed_at must be ISO-8601") from exc

    limitations: list[str] = []
    artifact_bound = str(receipt["package_sha256"]) == expected_package_sha256
    prescription_bound = str(receipt["prescription_digest"]) == expected_prescription_digest
    identity_ok = receipt.get("device_identity_verified") is True
    if not artifact_bound:
        limitations.append("package_digest_mismatch")
    if not prescription_bound:
        limitations.append("prescription_digest_mismatch")
    if not identity_ok:
        limitations.append("device_identity_not_verified")

    expected: dict[str, tuple[float, str]] = {}
    for idx, zone in enumerate(expected_zones, start=1):
        if not isinstance(zone, dict):
            continue
        zid = str(zone.get("zone_id") or f"ZN{idx}")
        try:
            rate = float(zone["rate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"expected zone {zid} has invalid rate") from exc
        unit = str(zone.get("unit") or "").strip()
        if not unit:
            raise ValueError(f"expected zone {zid} has no unit")
        expected[zid] = (rate, unit)
    if not expected:
        raise ValueError("expected_zones must contain at least one zone")

    applied = receipt.get("applied_zones")
    if not isinstance(applied, list):
        raise ValueError("receipt applied_zones must be a list")
    actual_by_id: dict[str, dict[str, Any]] = {}
    for row in applied:
        if not isinstance(row, dict) or not _nonempty(row.get("zone_id")):
            continue
        actual_by_id[str(row["zone_id"])] = row

    variances: list[ZoneVariance] = []
    for zid, (expected_rate, expected_unit) in expected.items():
        row = actual_by_id.get(zid)
        if row is None:
            limitations.append(f"zone_missing_from_receipt:{zid}")
            continue
        if str(row.get("unit") or "").strip() != expected_unit:
            limitations.append(f"zone_unit_mismatch:{zid}")
            continue
        try:
            actual_rate = float(row["actual_rate"])
        except (KeyError, TypeError, ValueError):
            limitations.append(f"zone_actual_rate_invalid:{zid}")
            continue
        if expected_rate == 0:
            variance_pct = 0.0 if actual_rate == 0 else float("inf")
        else:
            variance_pct = abs(actual_rate - expected_rate) / abs(expected_rate) * 100.0
        within = variance_pct <= allowed_rate_variance_pct
        variances.append(
            ZoneVariance(
                zone_id=zid,
                expected_rate=expected_rate,
                actual_rate=actual_rate,
                unit=expected_unit,
                variance_pct=round(variance_pct, 4),
                within_tolerance=within,
            )
        )
        if not within:
            limitations.append(f"zone_rate_variance_exceeded:{zid}")

    all_zones_accounted = len(variances) == len(expected)
    bound = artifact_bound and prescription_bound and identity_ok and all_zones_accounted
    # A rate variance is a verified failure, not "unverified". It remains outcome-eligible
    # because the artifact/device/zone evidence is complete and can teach from failure.
    rates_ok = all(z.within_tolerance for z in variances)
    verification_state = (
        "verified_success" if bound and rates_ok else "verified_failure" if bound else "unverified"
    )

    body = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "package_sha256": expected_package_sha256,
        "prescription_digest": expected_prescription_digest,
        "receipt_id": str(receipt["receipt_id"]),
        "observed_at": str(receipt["observed_at"]),
        "device_id": str(receipt["device_id"]),
        "device_identity_verified": identity_ok,
        "verification_state": verification_state,
        "zone_variances": [asdict(v) for v in variances],
        "limitations": limitations,
        "outcome_eligible": bound,
    }
    return MachineryAsAppliedTruth(**body, as_applied_digest=_digest(body))

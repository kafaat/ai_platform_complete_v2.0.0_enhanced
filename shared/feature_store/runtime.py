from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{sha256(raw).hexdigest()[:14]}"


def _parse_aware_time(value: Any) -> tuple[datetime | None, str]:
    """Parse a timestamp for a point-in-time decision without guessing its zone.

    Returns ``(dt, status)``: status is ``ok``, ``missing``, ``invalid`` or
    ``naive``. A naive timestamp is never read as UTC: its instant is ambiguous
    (a UTC+3 local clock shifts it by three hours), so it cannot place a row on
    either side of an as-of time. An aware value is returned in UTC.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "missing"
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None, "invalid"
    else:
        return None, "invalid"
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None, "naive"
    return dt.astimezone(UTC), "ok"


def _parse_time(value: Any) -> datetime | None:
    """Parse an explicit timezone-aware timestamp; never assume UTC for a naive value."""
    return _parse_aware_time(value)[0]


def _legacy_event_time_text(value: Any) -> str | None:
    """The event_time text stored in an offline manifest, as it was always written.

    Used only for the manifest content (and so its hash and dataset_version_id),
    never for a point-in-time decision: a manifest of legacy rows keeps the hash
    it had before the temporal checks existed. Safety is decided elsewhere.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _timestamped_features(
    rec: Any, *, as_of: datetime | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate the lineage and the availability of *every* feature of one row.

    Returns ``(validated, None)`` or ``(None, reason)``. A row is usable only with
    tenant, entity and ``source_version``; a non-empty feature map with finite
    values; timezone-aware ``event_time``, ``ingested_at`` and ``prediction_at``;
    and either a row-wide ``available_at`` or a ``feature_available_at`` map that
    names every feature. Each feature must satisfy
    ``event_time <= available <= ingested_at <= prediction_at`` and, with
    ``as_of``, be available, ingested and predicted at or before it. Neither
    ``event_time`` nor ``created_at`` stands in for a missing availability.

    This is a chronology guard, NOT proof that the caller's timestamps are
    authentic; trusted source receipts and tenant authorization stay separate.
    """
    if not isinstance(rec, dict):
        return None, "record_invalid"
    tenant = rec.get("tenant_id")
    entity = rec.get("entity_id")
    source = rec.get("source_version")
    if not all(isinstance(value, str) and value.strip() for value in (tenant, entity, source)):
        return None, "lineage_missing"
    features = rec.get("features")
    if (
        not isinstance(features, dict)
        or not features
        or any(
            not isinstance(key, str)
            or not key
            or (isinstance(value, float) and not math.isfinite(value))
            for key, value in features.items()
        )
    ):
        return None, "features_invalid"
    per_feature = rec.get("feature_available_at")
    single = rec.get("available_at")
    stamps = [rec.get("event_time"), rec.get("ingested_at"), rec.get("prediction_at"), single]
    if isinstance(per_feature, dict):
        stamps.extend(per_feature.values())
    if any(_parse_aware_time(value)[1] == "naive" for value in stamps):
        return None, "naive_timestamp"
    event = _parse_time(rec.get("event_time"))
    if event is None:
        return None, "event_time_missing_or_invalid"
    prediction = _parse_time(rec.get("prediction_at"))
    if prediction is None:
        return None, "prediction_time_missing_or_invalid"
    ingested = _parse_time(rec.get("ingested_at"))
    if ingested is None:
        return None, "ingestion_time_missing_or_invalid"
    if per_feature is not None and not isinstance(per_feature, dict):
        return None, "availability_invalid"
    if per_feature is None and single is None:
        return None, "availability_missing"
    if per_feature is not None and set(per_feature) != set(features):
        return None, "availability_missing"
    available: dict[str, datetime] = {}
    for name in features:
        stamp = _parse_time(per_feature[name] if per_feature is not None else single)
        if stamp is None:
            return None, "availability_missing_or_invalid"
        available[name] = stamp
        if stamp < event:
            return None, "available_before_event"
        if not stamp <= ingested <= prediction:
            return None, "feature_not_available_at_prediction"
        if as_of is not None and stamp > as_of:
            return None, "feature_not_available_at_snapshot"
    if as_of is not None and (ingested > as_of or prediction > as_of):
        return None, "ingestion_or_prediction_after_snapshot"
    return {
        "tenant_id": tenant,
        "entity_type": str(rec.get("entity_type") or "field"),
        "entity_id": entity,
        "source_version": source,
        "event_time": event,
        "prediction_at": prediction,
        "ingested_at": ingested,
        "available_at": available,
        "features": features,
        "feature_id": rec.get("feature_id"),
    }, None


def _reason_counts(reasons: Counter[str]) -> dict[str, int]:
    """The named per-reason counters every point-in-time output carries."""
    return {
        "missing_available_at_count": reasons["availability_missing"],
        "invalid_available_at_count": reasons["availability_missing_or_invalid"]
        + reasons["availability_invalid"],
        "naive_timestamp_count": reasons["naive_timestamp"],
        "available_before_event_count": reasons["available_before_event"],
    }


def resolve_learning_as_of(records: list[dict[str, Any]], *, now: datetime | None = None) -> str:
    """As-of time for a learning cycle: the latest aware ``prediction_at``, capped at now.

    ``prediction_at`` is the decision time each row was built for, so the
    snapshot (which needs ingestion and prediction at or before as-of) can keep
    rows. The cap at now stops a future-dated row from moving the as-of time
    forward and so certifying its own future availability. Naive or unparseable
    values are ignored, and so is order-by-string: offsets are compared as
    instants. With no usable ``prediction_at`` the as-of time is now.
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    aware = [
        dt
        for dt in (_parse_time(r.get("prediction_at")) for r in records if isinstance(r, dict))
        if dt is not None
    ]
    latest = max(aware, default=current)
    return min(latest, current).isoformat()


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    name: str
    version: str
    entity_type: str
    value_type: str
    owner: str
    ttl_hours: int
    sources: list[str] = field(default_factory=list)
    transformations: list[str] = field(default_factory=list)
    quality_gates: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)


@dataclass(frozen=True)
class FeatureSetManifest:
    feature_set_id: str
    name: str
    version: str
    entity_type: str
    feature_ids: list[str]
    feature_names: list[str]
    registry_version: str
    created_at: str


def _infer_value_type(values: list[Any]) -> str:
    typed = [v for v in values if v is not None]
    if not typed:
        return "unknown"
    if all(isinstance(v, bool) for v in typed):
        return "bool"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in typed):
        return "int"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in typed):
        return "float"
    return "string"


def register_feature_definitions(
    records: list[dict[str, Any]],
    *,
    name: str = "canonical_field_features",
    version: str = "v1",
    owner: str = "phase10",
    ttl_hours: int = 24,
    entity_type: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic feature registry manifest from feature records.

    This does not mutate storage. Persistence adapters should store the returned
    manifest into `feature_definitions` and `feature_versions`.
    """
    values_by_name: dict[str, list[Any]] = {}
    resolved_entity_type = entity_type or "field"
    for rec in records:
        resolved_entity_type = str(rec.get("entity_type") or resolved_entity_type)
        for key, value in (rec.get("features") or {}).items():
            values_by_name.setdefault(str(key), []).append(value)
    definitions: list[FeatureDefinition] = []
    for fname in sorted(values_by_name):
        payload = {
            "name": fname,
            "version": version,
            "entity_type": resolved_entity_type,
            "owner": owner,
        }
        definitions.append(
            FeatureDefinition(
                feature_id=_stable_id(payload, "featdef"),
                name=fname,
                version=version,
                entity_type=resolved_entity_type,
                value_type=_infer_value_type(values_by_name[fname]),
                owner=owner,
                ttl_hours=ttl_hours,
                sources=["phase9.feature_store_batch"],
                transformations=["canonical_normalization", "quality_gate_validation"],
                quality_gates={"not_null_preferred": True, "point_in_time_required": True},
            )
        )
    manifest = FeatureSetManifest(
        feature_set_id=_stable_id(
            {"name": name, "version": version, "features": [d.feature_id for d in definitions]},
            "fset",
        ),
        name=name,
        version=version,
        entity_type=resolved_entity_type,
        feature_ids=[d.feature_id for d in definitions],
        feature_names=[d.name for d in definitions],
        registry_version="feature-store.v1",
        created_at=_now(),
    )
    return {"feature_set": asdict(manifest), "definitions": [asdict(d) for d in definitions]}


_OPTIONAL_MANIFEST_KEYS = (
    "tenant_id",
    "available_at",
    "feature_available_at",
    "ingested_at",
    "prediction_at",
    "source_version",
)


def write_offline_feature_dataset(
    records: list[dict[str, Any]],
    *,
    feature_set_id: str,
    dataset_name: str = "phase10_training_dataset",
    version: str = "v1",
    object_uri: str | None = None,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Build an immutable offline dataset manifest with fail-closed temporal evidence.

    ``point_in_time_safe`` is true only when the dataset is non-empty, single
    tenant, ``as_of`` is a timezone-aware time, and every row passes
    ``_timestamped_features`` against that ``as_of``. Without ``as_of`` the rows
    are still checked, but no point-in-time claim is made: an internally ordered
    row can still have been published after the decision it trains for.

    ``unsafe_reason_counts`` counts row-level failures; ``pit_unsafe_reasons``
    lists every failed condition, the as-of ones included. It is a chronology
    assertion about supplied metadata, not attestation of real sensors nor a
    trainability decision. Rows are kept either way: a manifest, not a filter.
    """
    as_of_dt, as_of_status = _parse_aware_time(as_of)
    normalized: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    tenant_ids: set[str] = set()
    for incoming in records:
        rec = incoming if isinstance(incoming, dict) else {}
        valid, failure = _timestamped_features(incoming, as_of=as_of_dt)
        if failure:
            reasons[failure] += 1
        elif valid:
            tenant_ids.add(valid["tenant_id"])
        row = {
            "entity_type": str(rec.get("entity_type") or "field"),
            "entity_id": str(rec.get("entity_id") or "unknown"),
            "feature_id": rec.get("feature_id"),
            "event_time": _legacy_event_time_text(rec.get("event_time")),
            "features": rec.get("features") or {},
            "labels": rec.get("labels") or {},
            "quality": rec.get("quality") or {},
        }
        # Lineage keys enter the content only when supplied, so a manifest of
        # legacy rows keeps its historical content_hash and dataset_version_id.
        for key in _OPTIONAL_MANIFEST_KEYS:
            if rec.get(key) is not None:
                row[key] = rec.get(key)
        normalized.append(row)
    if len(tenant_ids) > 1:
        reasons["mixed_tenants"] += 1
    pit_reasons: list[str] = []
    if as_of_status != "ok":
        pit_reasons.append("as_of_" + as_of_status)
    if not normalized:
        pit_reasons.append("empty_dataset")
    pit_reasons.extend(sorted(reasons))
    content_hash = sha256(
        json.dumps(normalized, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    entities = {r["entity_id"] for r in normalized if r["entity_id"] != "unknown"}
    rows_safe = bool(normalized) and not reasons
    safe = rows_safe and as_of_dt is not None
    return {
        "dataset_version_id": _stable_id(
            {"feature_set_id": feature_set_id, "hash": content_hash, "version": version}, "dsver"
        ),
        "dataset_name": dataset_name,
        "version": version,
        "feature_set_id": feature_set_id,
        "row_count": len(normalized),
        "entity_count": len(entities),
        "content_hash": content_hash,
        "object_uri": object_uri,
        "as_of": as_of_dt.isoformat() if as_of_dt else None,
        "point_in_time_safe": safe,
        "temporal_integrity": "chronology_checked" if rows_safe else "blocked",
        "unsafe_reason_counts": dict(sorted(reasons.items())),
        "pit_unsafe_reasons": pit_reasons,
        "missing_event_time_count": sum(
            1
            for r in records
            if not isinstance(r, dict) or _parse_time(r.get("event_time")) is None
        ),
        **_reason_counts(reasons),
        # None when there is no usable as_of: "zero future rows" cannot be known.
        "future_available_count": (
            reasons["feature_not_available_at_snapshot"] if as_of_dt is not None else None
        ),
        "created_at": _now(),
    }


def build_point_in_time_snapshot(
    records: list[dict[str, Any]], *, as_of: str, max_age_hours: int = 48
) -> dict[str, Any]:
    """Select each feature separately, as known at or before ``as_of``.

    Keys are (tenant, entity_type, entity_id, feature). A row is excluded, and
    counted in ``exclusion_reasons``, when ``_timestamped_features`` rejects it
    against ``as_of`` (missing lineage or availability, a naive timestamp, a
    feature published, ingested or predicted after ``as_of``) or when its event
    is older than ``max_age_hours``. A row with no ``available_at`` is excluded
    (``missing_available_at_count``), never kept on its event time alone.

    ``as_of`` must be a timezone-aware ISO-8601 timestamp.
    """
    as_of_dt, as_of_status = _parse_aware_time(as_of)
    if as_of_dt is None:
        if as_of_status == "naive":
            raise ValueError("as_of must be a timezone-aware ISO-8601 timestamp")
        raise ValueError("as_of must be a timezone-aware ISO-8601 timestamp (missing or invalid)")
    if isinstance(max_age_hours, bool) or max_age_hours < 0:
        raise ValueError("max_age_hours must be non-negative")
    latest: dict[
        tuple[str, str, str, str], tuple[datetime, datetime, str, Any, dict[str, Any]]
    ] = {}
    reasons: Counter[str] = Counter()
    for rec in records:
        validated, failure = _timestamped_features(rec, as_of=as_of_dt)
        if failure:
            reasons[failure] += 1
            continue
        assert validated is not None
        event = validated["event_time"]
        if (as_of_dt - event).total_seconds() > max_age_hours * 3600:
            reasons["feature_stale"] += 1
            continue
        for name, value in validated["features"].items():
            key = (validated["tenant_id"], validated["entity_type"], validated["entity_id"], name)
            ordering = (event, validated["available_at"][name], validated["source_version"])
            if key not in latest or ordering > latest[key][:3]:
                latest[key] = (*ordering, value, validated)
    by_entity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (tenant_id, entity_type, entity_id, feature), (
        event,
        available,
        _,
        value,
        validated,
    ) in sorted(latest.items()):
        row = by_entity.setdefault(
            (tenant_id, entity_type, entity_id),
            {
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "event_time": None,
                "available_at": None,
                "features": {},
                "feature_provenance": {},
            },
        )
        row["features"][feature] = value
        row["feature_provenance"][feature] = {
            "event_time": event.isoformat(),
            "available_at": available.isoformat(),
            "ingested_at": validated["ingested_at"].isoformat(),
            "source_version": validated["source_version"],
        }
        # Row-level summaries: the newest event and the latest availability of
        # any selected feature (all are <= as_of by construction).
        if row["event_time"] is None or event.isoformat() > row["event_time"]:
            row["event_time"] = event.isoformat()
        if row["available_at"] is None or available.isoformat() > row["available_at"]:
            row["available_at"] = available.isoformat()
    rows = list(by_entity.values())
    return {
        "snapshot_id": _stable_id(
            {"as_of": as_of_dt.isoformat(), "rows": rows, "max_age_hours": max_age_hours}, "pit"
        ),
        "as_of": as_of_dt.isoformat(),
        "row_count": len(rows),
        "excluded_count": sum(reasons.values()),
        "exclusion_reasons": dict(sorted(reasons.items())),
        **_reason_counts(reasons),
        "future_available_count": reasons["feature_not_available_at_snapshot"],
        "rows": rows,
        "created_at": _now(),
    }


def materialize_online_feature_values(
    records: list[dict[str, Any]], *, feature_set_id: str
) -> dict[str, Any]:
    """Create online-write candidates without inventing missing event timestamps.

    The result is a candidate materialization, not proof of freshness. Inference
    must enforce its own decision-time freshness policy before consuming values.
    Labels are intentionally omitted from online inference feature writes.
    """
    latest: dict[
        tuple[str, str, str, str], tuple[datetime, datetime, str, Any, dict[str, Any]]
    ] = {}
    excluded: Counter[str] = Counter()
    now = datetime.now(UTC)
    for rec in records:
        valid, failure = _timestamped_features(rec, as_of=now)
        if failure:
            excluded[failure] += 1
            continue
        assert valid is not None
        for name, value in valid["features"].items():
            key = (valid["tenant_id"], valid["entity_type"], valid["entity_id"], name)
            ordering = (valid["event_time"], valid["available_at"][name], valid["source_version"])
            if key not in latest or ordering > latest[key][:3]:
                latest[key] = (*ordering, value, valid)
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (tenant, entity_type, entity_id, name), (event, available, _, value, valid) in sorted(
        latest.items()
    ):
        row = grouped.setdefault(
            (tenant, entity_type, entity_id),
            {
                "online_key": f"{feature_set_id}:{tenant}:{entity_type}:{entity_id}",
                "feature_set_id": feature_set_id,
                "tenant_id": tenant,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "values": {},
                "feature_provenance": {},
            },
        )
        row["values"][name] = value
        row["feature_provenance"][name] = {
            "event_time": event.isoformat(),
            "available_at": available.isoformat(),
            "ingested_at": valid["ingested_at"].isoformat(),
            "source_version": valid["source_version"],
        }
    writes = list(grouped.values())
    return {
        "materialization_id": _stable_id(
            {"feature_set_id": feature_set_id, "writes": writes}, "onmat"
        ),
        "feature_set_id": feature_set_id,
        "write_count": len(writes),
        "writes": writes,
        "excluded_count": sum(excluded.values()),
        "exclusion_reasons": dict(sorted(excluded.items())),
        "freshness_checked": False,
        "created_at": _now(),
    }


def build_feature_lineage_manifest(
    *,
    feature_set: dict[str, Any],
    definitions: list[dict[str, Any]],
    dataset_version: dict[str, Any] | None = None,
    consumers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "feature_set_id": feature_set.get("feature_set_id"),
        "feature_names": feature_set.get("feature_names") or [d.get("name") for d in definitions],
        "definitions": [
            {
                "feature_id": d.get("feature_id"),
                "name": d.get("name"),
                "sources": d.get("sources", []),
                "transformations": d.get("transformations", []),
            }
            for d in definitions
        ],
        "dataset_version_id": (dataset_version or {}).get("dataset_version_id"),
        "consumers": consumers or [],
    }
    payload["lineage_id"] = _stable_id(payload, "flin")
    payload["created_at"] = _now()
    return payload

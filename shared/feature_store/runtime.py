from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{sha256(raw).hexdigest()[:14]}"


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except Exception:
        return None


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


def write_offline_feature_dataset(
    records: list[dict[str, Any]],
    *,
    feature_set_id: str,
    dataset_name: str = "phase10_training_dataset",
    version: str = "v1",
    object_uri: str | None = None,
) -> dict[str, Any]:
    """Build an immutable offline dataset manifest with point-in-time metadata."""
    normalized: list[dict[str, Any]] = []
    missing_event_time = 0
    for rec in records:
        event_time = _parse_time(rec.get("event_time"))
        if event_time is None:
            missing_event_time += 1
        normalized.append(
            {
                "entity_type": str(rec.get("entity_type") or "field"),
                "entity_id": str(rec.get("entity_id") or "unknown"),
                "feature_id": rec.get("feature_id"),
                "event_time": event_time.isoformat() if event_time else None,
                "features": rec.get("features") or {},
                "labels": rec.get("labels") or {},
                "quality": rec.get("quality") or {},
            }
        )
    content_hash = sha256(
        json.dumps(normalized, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    entities = {r["entity_id"] for r in normalized if r["entity_id"] != "unknown"}
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
        "point_in_time_safe": missing_event_time == 0,
        "missing_event_time_count": missing_event_time,
        "created_at": _now(),
    }


def build_point_in_time_snapshot(
    records: list[dict[str, Any]], *, as_of: str, max_age_hours: int = 48
) -> dict[str, Any]:
    """Return latest feature row per entity at or before `as_of`.

    Records without parseable event_time are excluded to prevent label leakage.
    """
    as_of_dt = _parse_time(as_of)
    if as_of_dt is None:
        raise ValueError("as_of must be an ISO-8601 timestamp")
    latest_by_entity: dict[tuple[str, str], tuple[datetime, dict[str, Any]]] = {}
    excluded = 0
    max_age_seconds = max_age_hours * 3600
    for rec in records:
        ts = _parse_time(rec.get("event_time"))
        if ts is None or ts > as_of_dt or (as_of_dt - ts).total_seconds() > max_age_seconds:
            excluded += 1
            continue
        key = (str(rec.get("entity_type") or "field"), str(rec.get("entity_id") or "unknown"))
        if key not in latest_by_entity or ts > latest_by_entity[key][0]:
            latest_by_entity[key] = (ts, rec)
    rows = []
    for (entity_type, entity_id), (ts, rec) in sorted(latest_by_entity.items()):
        rows.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "event_time": ts.isoformat(),
                "features": rec.get("features") or {},
            }
        )
    return {
        "snapshot_id": _stable_id(
            {"as_of": as_of_dt.isoformat(), "rows": rows, "max_age_hours": max_age_hours}, "pit"
        ),
        "as_of": as_of_dt.isoformat(),
        "row_count": len(rows),
        "excluded_count": excluded,
        "rows": rows,
        "created_at": _now(),
    }


def materialize_online_feature_values(
    records: list[dict[str, Any]], *, feature_set_id: str
) -> dict[str, Any]:
    """Build latest online values per entity for Redis/Postgres online store."""
    latest: dict[tuple[str, str], tuple[datetime, dict[str, Any]]] = {}
    for rec in records:
        ts = _parse_time(rec.get("event_time")) or datetime.now(UTC)
        key = (str(rec.get("entity_type") or "field"), str(rec.get("entity_id") or "unknown"))
        if key not in latest or ts >= latest[key][0]:
            latest[key] = (ts, rec)
    writes = []
    for (entity_type, entity_id), (ts, rec) in sorted(latest.items()):
        writes.append(
            {
                "online_key": f"{feature_set_id}:{entity_type}:{entity_id}",
                "feature_set_id": feature_set_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "event_time": ts.isoformat(),
                "values": rec.get("features") or {},
                "labels": rec.get("labels") or {},
                "quality": rec.get("quality") or {},
            }
        )
    return {
        "materialization_id": _stable_id(
            {"feature_set_id": feature_set_id, "writes": writes}, "onmat"
        ),
        "feature_set_id": feature_set_id,
        "write_count": len(writes),
        "writes": writes,
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

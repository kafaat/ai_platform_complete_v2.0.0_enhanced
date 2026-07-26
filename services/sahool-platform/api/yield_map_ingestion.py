"""Pure contracts and parsers for PA-003 yield-map ingestion.

The module deliberately performs no database or HTTP I/O.  It accepts either a
GeoJSON FeatureCollection of Point features or CSV text, validates every record,
and emits a deterministic canonical representation used by the persistence
router.  Keeping parsing pure makes the untrusted-input boundary directly
unit-testable.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

PARSER_VERSION = "yield-map-v1"
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 20_000
MAX_YIELD_KG_HA = 100_000.0


class YieldMapFormat(str, Enum):
    GEOJSON = "geojson"
    CSV = "csv"


class YieldMapColumnMapping(BaseModel):
    longitude: str = "longitude"
    latitude: str = "latitude"
    yield_kg_ha: str = "yield_kg_ha"
    moisture_pct: str = "moisture_pct"
    harvested_at: str = "harvested_at"
    source_record_id: str = "source_record_id"


class YieldMapIngestRequest(BaseModel):
    season_id: str | None = Field(default=None, max_length=50)
    source_name: str = Field(min_length=1, max_length=255)
    source_format: YieldMapFormat
    source_crs: str = Field(default="EPSG:4326", pattern=r"^EPSG:4326$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] | str
    column_mapping: YieldMapColumnMapping = Field(default_factory=YieldMapColumnMapping)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("idempotency_key must not be blank")
        return normalized

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("metadata exceeds 64 KiB")
        return value


class CanonicalYieldRecord(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=160)
    longitude: float
    latitude: float
    yield_kg_ha: float
    moisture_pct: float | None = None
    harvested_at: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ParsedYieldMap(BaseModel):
    parser_version: str = PARSER_VERSION
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: list[CanonicalYieldRecord]


class YieldMapIngestionSummary(BaseModel):
    ingestion_id: str
    field_id: str
    season_id: str | None = None
    source_name: str
    source_format: YieldMapFormat
    source_crs: str
    source_sha256: str
    parser_version: str
    idempotency_key: str
    record_count: int
    min_yield_kg_ha: float | None = None
    max_yield_kg_ha: float | None = None
    mean_yield_kg_ha: float | None = None
    created_at: str | None = None
    replayed: bool = False


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_bytes(payload: dict[str, Any] | str) -> bytes:
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = _canonical_json(payload).encode("utf-8")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    return raw


def _number(value: Any, field_name: str, *, required: bool = True) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if number != number or number in {float("inf"), float("-inf")}:
        raise ValueError(f"{field_name} must be finite")
    return number


def _timestamp(value: Any) -> datetime | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("harvested_at must be ISO-8601") from exc


def _canonical_record(
    *,
    source_record_id: Any,
    longitude: Any,
    latitude: Any,
    yield_kg_ha: Any,
    moisture_pct: Any,
    harvested_at: Any,
    attributes: dict[str, Any],
) -> CanonicalYieldRecord:
    lon = _number(longitude, "longitude")
    lat = _number(latitude, "latitude")
    yield_value = _number(yield_kg_ha, "yield_kg_ha")
    moisture = _number(moisture_pct, "moisture_pct", required=False)
    assert lon is not None and lat is not None and yield_value is not None
    if not -180 <= lon <= 180:
        raise ValueError("longitude must be between -180 and 180")
    if not -90 <= lat <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not 0 < yield_value <= MAX_YIELD_KG_HA:
        raise ValueError(f"yield_kg_ha must be > 0 and <= {MAX_YIELD_KG_HA:g}")
    if moisture is not None and not 0 <= moisture <= 100:
        raise ValueError("moisture_pct must be between 0 and 100")

    record_id = str(source_record_id).strip()
    if not record_id:
        raise ValueError("source_record_id must not be blank")
    harvested_timestamp = _timestamp(harvested_at)
    canonical = {
        "source_record_id": record_id,
        "longitude": lon,
        "latitude": lat,
        "yield_kg_ha": yield_value,
        "moisture_pct": moisture,
        "harvested_at": harvested_timestamp.isoformat() if harvested_timestamp else None,
        "attributes": attributes,
    }
    digest = hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()
    return CanonicalYieldRecord(
        source_record_id=record_id,
        longitude=lon,
        latitude=lat,
        yield_kg_ha=yield_value,
        moisture_pct=moisture,
        harvested_at=harvested_timestamp,
        attributes=attributes,
        record_sha256=digest,
    )


def _parse_geojson(payload: dict[str, Any]) -> list[CanonicalYieldRecord]:
    if payload.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON payload must be a FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("GeoJSON FeatureCollection must contain features")
    if len(features) > MAX_RECORDS:
        raise ValueError(f"record count exceeds {MAX_RECORDS}")

    records: list[CanonicalYieldRecord] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"feature {index} is not a GeoJSON Feature")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise ValueError(f"feature {index} geometry must be Point")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError(f"feature {index} Point coordinates are invalid")
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            raise ValueError(f"feature {index} properties must be an object")
        record_id = feature.get("id") or properties.get("source_record_id") or f"feature-{index}"
        core_keys = {"source_record_id", "yield_kg_ha", "moisture_pct", "harvested_at"}
        attributes = {key: value for key, value in properties.items() if key not in core_keys}
        records.append(
            _canonical_record(
                source_record_id=record_id,
                longitude=coordinates[0],
                latitude=coordinates[1],
                yield_kg_ha=properties.get("yield_kg_ha"),
                moisture_pct=properties.get("moisture_pct"),
                harvested_at=properties.get("harvested_at"),
                attributes=attributes,
            )
        )
    return records


def _parse_csv(payload: str, mapping: YieldMapColumnMapping) -> list[CanonicalYieldRecord]:
    reader = csv.DictReader(io.StringIO(payload))
    if reader.fieldnames is None:
        raise ValueError("CSV header is required")
    required_columns = {mapping.longitude, mapping.latitude, mapping.yield_kg_ha}
    missing = sorted(required_columns - set(reader.fieldnames))
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

    records: list[CanonicalYieldRecord] = []
    mapped_columns = {
        mapping.longitude,
        mapping.latitude,
        mapping.yield_kg_ha,
        mapping.moisture_pct,
        mapping.harvested_at,
        mapping.source_record_id,
    }
    for index, row in enumerate(reader, start=1):
        if index > MAX_RECORDS:
            raise ValueError(f"record count exceeds {MAX_RECORDS}")
        record_id = row.get(mapping.source_record_id) or f"row-{index}"
        attributes = {key: value for key, value in row.items() if key not in mapped_columns}
        records.append(
            _canonical_record(
                source_record_id=record_id,
                longitude=row.get(mapping.longitude),
                latitude=row.get(mapping.latitude),
                yield_kg_ha=row.get(mapping.yield_kg_ha),
                moisture_pct=row.get(mapping.moisture_pct),
                harvested_at=row.get(mapping.harvested_at),
                attributes=attributes,
            )
        )
    if not records:
        raise ValueError("CSV must contain at least one data row")
    return records


def parse_yield_map(request: YieldMapIngestRequest) -> ParsedYieldMap:
    """Validate and canonicalize an untrusted yield-map payload."""

    raw = _source_bytes(request.payload)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    if request.source_format is YieldMapFormat.GEOJSON:
        if not isinstance(request.payload, dict):
            raise ValueError("GeoJSON payload must be an object")
        records = _parse_geojson(request.payload)
    else:
        if not isinstance(request.payload, str):
            raise ValueError("CSV payload must be text")
        records = _parse_csv(request.payload, request.column_mapping)

    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        if record.source_record_id in seen:
            duplicates.add(record.source_record_id)
        seen.add(record.source_record_id)
    if duplicates:
        sample = ", ".join(sorted(duplicates)[:5])
        raise ValueError(f"duplicate source_record_id values: {sample}")
    return ParsedYieldMap(source_sha256=source_sha256, records=records)

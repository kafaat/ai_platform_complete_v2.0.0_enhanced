"""Canonical observation store (W1-11, owner decision 2026-11-16).

indicators-service owns ``canonical_observations`` (migrations/v286): one append-only row per
raster product that raster-service published. raster-service pushes it over HTTP
(``POST /internal/v1/observations``) and never writes the table itself.

Identity: ``observation_id`` is the asset stable id the canonical contract already uses
(``observation_runtime.asset_stable_id``: tenant, field, scene, indicator, acquisition instant).
``acquisition_day_id`` is the id raster's computed path gives the same asset after a restart,
when its layer only carries the acquisition DATE; a read or a join by either id finds the row.
``revision_key`` is the product revision it was published under (geometry revision, algorithm
version, QA mask version, raster product identity): a boundary edit or a reprocess of the same
scene is a new revision of the same observation, stored as a new row. Content:
``payload_sha256`` over the observation's content, without the delivery metadata
(``DELIVERY_FIELDS``) that changes when the same COG is rewritten. Same id, same revision and same
content is a replay; same id, same revision and other content is a conflict and nothing is stored.

Reads never decide on their own which product is current: raster-service's asset lifecycle does
(``ready`` vs ``stale``). The read routes ask raster-service as before and serve, for every asset
it still publishes, the stored row of that exact asset and revision (``match_bundle_item``,
``merge_timeline_points``); an asset with no stored row is served from the computed path, and says
so. A stored row of a stale geometry or a superseded reprocess is therefore never served.

Numbers stay numbers: the payload is validated with strict, finite floats (decimal text such as
``"0.61"`` is refused) and lands in NUMERIC columns and JSON numbers. That keeps gap
CANONICAL-DECIMAL-ARRIVES-AS-TEXT-AND-DROPS-NDVI-01 closed on this path.

Reads return ``None`` when the store is not configured or not reachable, so the routes keep their
computed path; writes fail closed (the route answers 503 and the raster outbox retries).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from observation_runtime import asset_day_id, asset_stable_id
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger("indicators-service.observation_store")

SCHEMA_VERSION = "sahool.published_observation/1"
#: Fields that describe this delivery of the asset, not the observation: a re-run of the same scene
#: rewrites the COG (new uri, new availability time, new job) without changing what was observed.
DELIVERY_FIELDS = frozenset({"data_available_at", "processing_job_id", "cog_uri"})

_Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
_Ratio = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=1)]


class ObservationStatsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean: _Number
    median: _Number | None = None
    p10: _Number | None = None
    p90: _Number | None = None
    std: _Number | None = None
    min: _Number | None = None
    max: _Number | None = None


class PublishedObservationV1(BaseModel):
    """What raster-service sends for one published asset (``raster_observation_outbox.payload``)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sahool.published_observation/1"] = SCHEMA_VERSION
    tenant_id: UUID
    field_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,50}$")
    indicator: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    scene_id: str = Field(min_length=1, max_length=256)
    acquired_at: datetime
    stats: ObservationStatsV1
    valid_pixel_ratio: _Ratio | None = None
    coverage_ratio: _Ratio | None = None
    cloud_pct: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=100)] | None = None
    quality_score: _Number | None = None
    quality_gate_passed: Annotated[bool, Field(strict=True)]
    index_quality_flags: tuple[str, ...] = ()
    algorithm_version: str | None = Field(default=None, max_length=128)
    qa_mask_version: str | None = Field(default=None, max_length=128)
    product_identity_key: str | None = Field(default=None, max_length=512)
    geometry_revision: Annotated[int, Field(strict=True, ge=0)] | None = None
    # delivery metadata — stored with the first delivery, outside the content hash
    data_available_at: datetime | None = None
    processing_job_id: str | None = Field(default=None, max_length=256)
    cog_uri: str | None = Field(default=None, max_length=2048)

    @field_validator("acquired_at", "data_available_at")
    @classmethod
    def _aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must carry a timezone")
        return value.astimezone(UTC)

    @field_validator("scene_id")
    @classmethod
    def _scene_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scene_id must not be blank")
        return value

    def observation_id(self) -> str:
        """The asset stable id ``canonicalize_bundle`` derives for the same observation."""
        return asset_stable_id(
            self.tenant_id, self.field_id, self.scene_id, self.indicator, self.acquired_at
        )

    def acquisition_day_id(self) -> str:
        """The id raster's computed path gives this asset after a restart (DATE-only layer)."""
        return asset_day_id(
            self.tenant_id, self.field_id, self.scene_id, self.indicator, self.acquired_at
        )

    def revision_key(self) -> str:
        """The product revision this observation was published under (see the module doc)."""
        identity = {
            "geometry_revision": self.geometry_revision,
            "algorithm_version": self.algorithm_version,
            "qa_mask_version": self.qa_mask_version,
            "product_identity_key": self.product_identity_key,
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def stored_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_sha256(self) -> str:
        content = self.model_dump(mode="json", exclude=set(DELIVERY_FIELDS))
        encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode()).hexdigest()


class StoreUnavailable(RuntimeError):
    """The store is not configured or not reachable; writes must fail closed."""


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "")


def configured() -> bool:
    return bool(_dsn())


async def _connect():
    dsn = _dsn()
    if not dsn:
        raise StoreUnavailable("DATABASE_URL is not configured")
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover — the image installs it
        raise StoreUnavailable("asyncpg is not installed") from exc
    try:
        return await asyncpg.connect(dsn, statement_cache_size=0, timeout=5)
    except Exception as exc:  # noqa: BLE001 — any connect failure is "unavailable"
        raise StoreUnavailable(f"store unreachable: {type(exc).__name__}") from exc


_INSERT = """
    INSERT INTO canonical_observations (
        tenant_id, observation_id, field_id, indicator_code, scene_id, acquired_at,
        mean, valid_pixel_ratio, coverage_ratio, cloud_pct, quality_gate_passed,
        geometry_revision, algorithm_version, qa_mask_version, product_identity_key,
        revision_key, acquisition_day_id, payload, payload_sha256
    ) VALUES (
        $1::uuid, $2, $3, $4, $5, $6,
        $7::numeric, $8::numeric, $9::numeric, $10::numeric, $11,
        $12, $13, $14, $15,
        $16, $17, $18::jsonb, $19
    )
    ON CONFLICT (tenant_id, observation_id, revision_key) DO NOTHING
    RETURNING published_at
"""

_SELECT_ONE = """
    SELECT payload_sha256, published_at FROM canonical_observations
    WHERE tenant_id = $1::uuid AND observation_id = $2 AND revision_key = $3
"""


async def insert_observation(record: PublishedObservationV1) -> dict[str, Any]:
    """Insert one observation idempotently.

    Returns ``{"status": "created"|"replayed"|"conflict", "observation_id", "revision_key",
    "payload_sha256", "stored_payload_sha256", "published_at"}``. Raises ``StoreUnavailable`` when it cannot answer.
    """
    observation_id = record.observation_id()
    revision = record.revision_key()
    digest = record.content_sha256()
    payload = record.stored_payload()
    tenant = str(record.tenant_id)
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            row = await conn.fetchrow(
                _INSERT,
                tenant,
                observation_id,
                record.field_id,
                record.indicator,
                record.scene_id,
                record.acquired_at,
                str(record.stats.mean),
                _num(record.valid_pixel_ratio),
                _num(record.coverage_ratio),
                _num(record.cloud_pct),
                record.quality_gate_passed,
                record.geometry_revision,
                record.algorithm_version,
                record.qa_mask_version,
                record.product_identity_key,
                revision,
                record.acquisition_day_id(),
                json.dumps(payload, sort_keys=True, allow_nan=False),
                digest,
            )
            if row is not None:
                return {
                    "status": "created",
                    "observation_id": observation_id,
                    "revision_key": revision,
                    "payload_sha256": digest,
                    "stored_payload_sha256": digest,
                    "published_at": row["published_at"],
                }
            existing = await conn.fetchrow(_SELECT_ONE, tenant, observation_id, revision)
    except StoreUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — a failed write is never reported as stored
        raise StoreUnavailable(f"store write failed: {type(exc).__name__}") from exc
    finally:
        await conn.close()
    if existing is None:  # the conflicting row is not visible to this tenant: never claim a replay
        raise StoreUnavailable("conflicting row not visible under the tenant")
    stored = existing["payload_sha256"]
    return {
        "status": "replayed" if stored == digest else "conflict",
        "observation_id": observation_id,
        "revision_key": revision,
        "payload_sha256": digest,
        "stored_payload_sha256": stored,
        "published_at": existing["published_at"],
    }


def _num(value: float | None) -> str | None:
    return None if value is None else str(value)


def _row(record: Any) -> dict[str, Any]:
    out = dict(record)
    payload = out.get("payload")
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode()
    if isinstance(payload, str):
        payload = json.loads(payload)
    out["payload"] = payload
    return out


_FOR_ASSETS = """
    SELECT observation_id, acquisition_day_id, indicator_code, scene_id, acquired_at,
           geometry_revision, algorithm_version, qa_mask_version, payload, published_at
    FROM canonical_observations
    WHERE tenant_id = $1::uuid AND field_id = $2
      AND (observation_id = ANY($3::text[]) OR acquisition_day_id = ANY($3::text[]))
    ORDER BY observation_id, published_at
"""

_BETWEEN = """
    SELECT observation_id, acquisition_day_id, indicator_code, scene_id, acquired_at,
           geometry_revision, algorithm_version, qa_mask_version, payload, published_at
    FROM canonical_observations
    WHERE tenant_id = $1::uuid AND field_id = $2 AND indicator_code = $3
      AND acquired_at >= $4 AND acquired_at < $5
    ORDER BY acquired_at, published_at
"""


async def _read(sql: str, tenant_id: UUID, *args: Any) -> list[dict[str, Any]] | None:
    if not configured():
        return None
    try:
        conn = await _connect()
    except StoreUnavailable as exc:
        logger.warning("canonical observation store unavailable for read: %s", exc)
        return None
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
            rows = await conn.fetch(sql, str(tenant_id), *args)
        return [_row(r) for r in rows]
    except Exception as exc:  # noqa: BLE001 — the read path declares its fallback
        logger.warning("canonical observation store read failed: %s", type(exc).__name__)
        return None
    finally:
        await conn.close()


async def observations_for_assets(
    *, tenant_id: UUID, field_id: str, observation_ids: list[str]
) -> list[dict[str, Any]] | None:
    """Every stored revision of these assets, named by either id raster's computed path uses
    (``observation_id`` or ``acquisition_day_id``); ``None`` when the store cannot answer."""
    return await _read(_FOR_ASSETS, tenant_id, field_id, list(observation_ids))


async def observations_between(
    *, tenant_id: UUID, field_id: str, indicator: str, start: datetime, end: datetime
) -> list[dict[str, Any]] | None:
    """Every stored row of one indicator acquired in ``[start, end)``; ``None`` when unavailable."""
    return await _read(_BETWEEN, tenant_id, field_id, indicator, start, end)


# ── projections onto the existing canonical converters ──────────────────────────────────────
def bundle_item(row: dict[str, Any]) -> dict[str, Any]:
    """The stored payload as the raster bundle item ``canonicalize_bundle`` reads."""
    p = row["payload"]
    acquired = p["acquired_at"]
    product: dict[str, Any] = {
        "source": "raster-service",
        "estimated": False,
        "real_data": True,
        "quality_gate_passed": p.get("quality_gate_passed") is True,
        "quality_score": p.get("quality_score"),
        "valid_pixel_ratio": p.get("valid_pixel_ratio"),
        "data_available_at": p.get("data_available_at"),
        "provenance": {
            "scene_id": p.get("scene_id"),
            "qa_mask_version": p.get("qa_mask_version"),
            "algorithm_version": p.get("algorithm_version"),
            "acquisition_datetime": acquired,
            "processing_job_id": p.get("processing_job_id"),
            "geometry_revision": p.get("geometry_revision"),
        },
    }
    return {
        "real_data": True,
        "date": acquired,
        "stats": dict(p.get("stats") or {}),
        "coverage_ratio": p.get("coverage_ratio"),
        "valid_pixel_ratio": p.get("valid_pixel_ratio"),
        "cloud_pct": p.get("cloud_pct"),
        "confidence": p.get("quality_score"),
        "index_quality_flags": list(p.get("index_quality_flags") or ()),
        "indicator_product": product,
    }


def _revision(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(rows, key=lambda r: r["published_at"]) if rows else None


def bundle_item_identity(item: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """The product revision of one raster bundle item: what a stored row must match exactly."""
    product = item.get("indicator_product") or {}
    provenance = product.get("provenance") or {}
    revision = _revision((item.get("grid_identity") or {}).get("geometry_revision"))
    if revision is None:
        revision = _revision(provenance.get("geometry_revision"))
    if revision is None:
        revision = _revision(bundle.get("field_revision"))
    return {
        "geometry_revision": revision,
        "algorithm_version": provenance.get("algorithm_version"),
        "qa_mask_version": provenance.get("qa_mask_version"),
    }


def match_bundle_item(
    rows: list[dict[str, Any]], *, observation_id: str, identity: dict[str, Any]
) -> dict[str, Any] | None:
    """The stored row of the asset raster-service serves now, at the revision it serves.

    Same asset (its id, or the id raster gives it after a restart), same geometry revision,
    same algorithm and QA mask version; the latest
    delivery of that revision wins. A row of another revision (an old boundary, an older
    algorithm) never matches, so it is never served in place of the current product. An unknown
    algorithm version on the raster side matches nothing: the computed path answers.
    """
    if identity.get("algorithm_version") is None:
        return None
    return _latest(
        [
            r
            for r in rows
            if observation_id in (r["observation_id"], r.get("acquisition_day_id"))
            and _revision(r.get("geometry_revision")) == identity["geometry_revision"]
            and r.get("algorithm_version") == identity["algorithm_version"]
            and r.get("qa_mask_version") == identity["qa_mask_version"]
        ]
    )


def _utc_day(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) == 10:
        return raw
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).date().isoformat()


def _day_start(day: str | None) -> datetime | None:
    if day is None:
        return None
    try:
        return datetime.fromisoformat(day + "T00:00:00+00:00")
    except ValueError:
        return None


def _stored_point(row: dict[str, Any], day: str) -> dict[str, Any]:
    p = row["payload"]
    stats = p.get("stats") or {}
    return {
        # The raster series is one point per UTC day; the stored point keeps that key so the
        # observation and asset references of the timeline do not depend on which source served.
        "datetime": day,
        "mean": stats.get("mean"),
        "stddev": stats.get("std"),
        "valid_pixel_ratio": p.get("valid_pixel_ratio"),
        "coverage_ratio": p.get("coverage_ratio"),
        "cloud_pct": p.get("cloud_pct"),
        "scene_id": p.get("scene_id"),
        "geometry_revision": p.get("geometry_revision"),
        # The product revision the raster point named (equal, since the row matched it): the
        # timeline's asset reference hashes algorithm_version, so both sources give one reference.
        "algorithm_version": p.get("algorithm_version"),
        "qa_mask_version": p.get("qa_mask_version"),
    }


def timeline_point_identity(point: dict[str, Any]) -> dict[str, Any]:
    """The product revision of one raster ``/timeseries`` point, in ``match_bundle_item``'s terms.

    raster-service's point carries the grid's geometry revision and the product's algorithm and
    QA mask versions (``raster_field_runtime._timeseries_point``). A point from a raster-service
    that does not report the algorithm version has ``None`` there and matches no stored row.
    """
    return {
        "geometry_revision": _revision(point.get("geometry_revision")),
        "algorithm_version": point.get("algorithm_version"),
        "qa_mask_version": point.get("qa_mask_version"),
    }


def merge_timeline_points(
    raster_points: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    tenant_id: UUID | str,
    field_id: str,
    indicator: str,
) -> tuple[list[dict[str, Any]], int]:
    """raster ``/timeseries`` points with each one replaced by its stored row when there is one.

    raster-service decides which days have a current product (its asset lifecycle drops stale
    geometries); the store supplies the published fact of that product. A raster point is
    replaced only by the stored row ``match_bundle_item`` selects for it, the rule the
    ``/observations`` route uses: the same asset (by the id raster's series gives a scene's UTC
    day) and the same product revision (geometry revision, algorithm version, QA mask version).
    A reprocess under a new algorithm whose push has not been stored, or was refused, therefore
    keeps raster's current value instead of the stored fact of the older revision. A point that
    names no scene is left as raster computed it. A stored row with no current raster point is
    not served: it belongs to a product raster-service no longer publishes. Returns the merged
    points and how many came from the store.
    """
    merged: list[dict[str, Any]] = []
    stored = 0
    for point in raster_points:
        day = _utc_day(point.get("datetime"))
        scene = point.get("scene_id")
        match = None
        acquired = _day_start(day)
        if acquired is not None and scene is not None:
            day_id = asset_day_id(tenant_id, field_id, scene, indicator, acquired)
            match = match_bundle_item(
                rows, observation_id=day_id, identity=timeline_point_identity(point)
            )
        if match is None or day is None:
            merged.append(point)
        else:
            merged.append(_stored_point(match, day))
            stored += 1
    return merged, stored

"""Resolve the canonical spectral state product for a field, server-side.

Peer of ``api/canonical_water_state.py`` and ``api/canonical_soil_state.py``: it answers
*"what does the platform actually know about this field's spectral indices right now"*
and returns either a canonical product or ``None``. It never computes a raster index and
never synthesizes a value to satisfy a contract.

**Why this module exists (P0-2, spectral half).** ``routers/internal_service.py`` composed
``canonical_field_state`` with ``spectral=None`` hard-coded, while a producer
(``core.crop_intelligence.build_canonical_spectral_state``) and a server-side resolver both
already existed — the latter living inside ``routers/crop_twin.py``, reachable only from
that router. So the composed canonical state declared ``spectral_missing`` for fields whose
indices the platform could read. The resolver moved here so both consumers share one
implementation rather than one of them owning it privately.

``ndvi`` is the master index: without it there is no server authority and the answer is
``None``. A product with every index ``None`` would be worse than absence — it would set
``availability.spectral = True`` while nothing is known, which is exactly the fabrication
``core/canonical_field_state.py`` exists to prevent.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from core.crop_intelligence import build_canonical_spectral_state

# المؤشّرات القانونيّة المُشتقّة خادميّاً (NDVI سيّد؛ إن غاب ⇒ لا سلطة خادميّة).
SERVER_SPECTRAL_INDICES = ("ndvi", "ndre", "ndmi", "msi")


def _finite_mean(value: object, index: str) -> float | None:
    """A numeric mean is not proof of quality, but invalid means are never used."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if index != "msi" and not -1.0 <= number <= 1.0:
        return None
    if index == "msi" and number < 0.0:
        return None
    return number


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= 4096 else None


def _index_record(data: dict, index: str) -> dict:
    """Preserve per-index lineage without forwarding arbitrary URLs or payloads.

    Values are provider-supplied metadata, not independently authenticated here.
    Missing metadata remains missing; in particular no master scene is borrowed.
    """
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    quality = _text(data.get("quality_status")) or "unknown"
    mean = _finite_mean(stats.get("mean"), index)
    if quality in {"invalid", "insufficient", "unavailable"}:
        mean = None
    record = {
        "value": mean,
        "scene_id": _text(data.get("scene_id")),
        "asset_id": _text(data.get("asset_id")),
        "product_id": _text(data.get("product_id")),
        "acquisition_date": _text(data.get("date")),
        "quality_status": quality,
        "source": _text(data.get("source")),
        "real_data": True,
        "metadata_independently_authenticated": False,
    }
    for name in ("input_checksum", "processing_version", "qa_mask_version"):
        record[name] = _text(data.get(name))
    revision = data.get("geometry_revision")
    record["geometry_revision"] = (
        revision if type(revision) is int and revision >= 0 else _text(revision)
    )
    for name in ("valid_pixel_ratio", "coverage_ratio"):
        value = data.get(name)
        if value is None:
            value = stats.get(name)
        number = _finite_mean(value, "msi")
        record[name] = number if number is not None and number <= 1.0 else None
    return record


async def _resolve_server_spectral(field_id: str, tenant_id: str | None) -> dict | None:
    """Fetch independent latest products; retain every contributing identity.

    NDVI remains the required master. Transport is a test seam, not a second
    raster engine. No acquisition compatibility is inferred from latest requests.
    """
    if not field_id:
        return None
    from api.raster_service_client import get_indicator_grid

    async def _one(index: str) -> dict | None:
        try:
            data = await get_indicator_grid(
                field_id, tenant_id=tenant_id, index=index, date="latest", timeout_s=20.0
            )
        except Exception:  # noqa: BLE001 -- transport failure means no observation
            return None
        if (
            not isinstance(data, dict)
            or data.get("real_data") is not True
            or data.get("source") == "simulation"
        ):
            return None
        # If the service supplies scope, it must not contradict the request.
        if data.get("field_id") is not None and data["field_id"] != field_id:
            return None
        if data.get("tenant_id") is not None and data["tenant_id"] != tenant_id:
            return None
        return _index_record(data, index)

    results = await asyncio.gather(*[_one(ix) for ix in SERVER_SPECTRAL_INDICES])
    records = {
        ix: record
        for ix, record in zip(SERVER_SPECTRAL_INDICES, results, strict=True)
        if record is not None
    }
    master = records.get("ndvi")
    if master is None or master["value"] is None:
        return None
    parsed = {ix: records.get(ix, {}).get("value") for ix in SERVER_SPECTRAL_INDICES}
    return {
        **parsed,
        "acquisition_date": master["acquisition_date"],  # legacy alias: NDVI only
        "scene_id": master["scene_id"] or master["asset_id"],
        "index_provenance": records,
        "source_authority": "raster-service",
    }


async def resolve_canonical_spectral_state(
    *, tenant_id: str | None, field_id: str
) -> dict[str, Any] | None:
    """Compose a read product. Authority is distinct from scientific quality.

    Keep temporal_compatible=None: per-index lineage does not by itself prove
    matching grids, masks, processing or dates. No new decision authorization.
    """
    if not field_id:
        return None
    server_spec = await _resolve_server_spectral(field_id, tenant_id)
    if server_spec is None:
        return None
    records = server_spec["index_provenance"]
    evidence_ids = list(
        dict.fromkeys(
            value
            for record in records.values()
            for key in ("product_id", "scene_id", "asset_id")
            if (value := record.get(key)) is not None
        )
    )
    # A mixed-quality product must never be upgraded by its authoritative source.
    values = [record for record in records.values() if record["value"] is not None]
    quality = (
        "validated"
        if values and all(record["quality_status"] == "validated" for record in values)
        else "unknown"
    )
    return build_canonical_spectral_state(
        ndvi=server_spec.get("ndvi"),
        ndre=server_spec.get("ndre"),
        ndmi=server_spec.get("ndmi"),
        msi=server_spec.get("msi"),
        acquisition_date=server_spec.get("acquisition_date"),
        product_ids=evidence_ids,
        quality_status=quality,
        temporal_compatible=None,
        index_provenance=records,
        source_authority="raster-service",
    )

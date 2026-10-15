"""Normalised fact layer. Generators only ever read from a FactStore, so the
same question code runs on PostGIS rows, GeoJSON fixtures or tests.

Contracts (0.2.0):
* Entity keys follow the database contract UNIQUE(field_id, tenant_id):
  a field is identified by "<tenant>::<field_id>" (NULL tenant = "∅").
* A record (soil reading / indicator) is admitted only if it is in the tenant
  scope AND its owning field (same tenant, same field_id) was loaded.
* Association between records and fields never crosses tenants.
* Timestamps are kept in full; nothing downstream depends on row order.
* Measurements failing quality control are removed from the usable value and
  kept in `qc` with the reason, so questions become abstentions.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .geo import Geometry

NULL_TENANT = "∅"


def tenant_key(t) -> str:
    return NULL_TENANT if t is None else str(t)


def make_key(tenant, field_id) -> str:
    return f"{tenant_key(tenant)}::{field_id}"


_TIME_OFFSET = re.compile(r"^(\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(?:([+-]\d{2}):?(\d{2})?)?$")


def parse_ts(v) -> dt.datetime | None:
    """Parse a timestamp keeping time and offset ('2022-09-07 00:00:00+00',
    '2026-03-12T16:00:00', '2025-01-01')."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    s = str(v).strip().replace("T", " ")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if len(s) > 10 and s[10] == " ":
        m = _TIME_OFFSET.match(s[11:])
        if m:
            s = f"{s[:10]} {m.group(1)}" + (
                f"{m.group(2)}:{m.group(3) or '00'}" if m.group(2) else ""
            )
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        try:
            return dt.datetime.fromisoformat(s[:10])
        except ValueError:
            return None


def to_date(v) -> dt.date | None:
    ts = parse_ts(v)
    return ts.date() if ts else None


def to_float(v) -> float | None:
    """Finite float or None (for descriptive attributes)."""
    f = to_float_raw(v)
    return f if f is not None and math.isfinite(f) else None


def to_float_raw(v) -> float | None:
    """Float including inf/nan (for measurements, so QC can see bad values)."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


EC_UNIT_FACTORS = {
    "ds/m": 1.0,
    "ms/cm": 1.0,
    "mmhos/cm": 1.0,
    "µs/cm": 0.001,
    "us/cm": 0.001,
    "μs/cm": 0.001,
}
# TDS reported as ppm / mg/L: EC (dS/m) ≈ TDS / 640 (FAO 29 Rev.1, valid roughly for EC < 5 dS/m).
# Approximate, so answers near a class boundary are not generated from it.
TDS_UNITS = {"ppm", "mg/l", "mg/liter", "ppmtds", "tds(ppm)"}
TDS_FACTOR = 1 / 640


@dataclass
class Field:
    id: str
    name: str
    tenant: str | None = None
    governorate: str | None = None
    crop: str | None = None
    soil_type: str | None = None
    area_ha_stored: float | None = None
    lat: float | None = None
    lon: float | None = None
    geom: Geometry | None = None  # usable geometry (None when missing or quarantined)
    db_area_m2: float | None = None  # PostGIS ST_Area(geography), if cross-checked
    geom_raw: Geometry | None = None  # as loaded, kept for audit when quarantined
    geom_problems: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return make_key(self.tenant, self.id)

    @property
    def display(self) -> str:
        return self.name or self.id


def _ts_iso(ts: dt.datetime | None) -> str:
    return ts.isoformat() if ts else ""


@dataclass
class SoilSample:
    sample_id: str
    field_id: str
    recorded_ts: dt.datetime | None
    ph: float | None = None
    ec: float | None = None
    moisture: float | None = None
    n: float | None = None
    p: float | None = None
    k: float | None = None
    om: float | None = None
    depth_cm: float | None = None
    source: str | None = None
    point: tuple[float, float] | None = None
    tenant: str | None = None
    record_id: str | None = None
    qc: dict = field(default_factory=dict)  # attr -> {"raw": value, "code": reason}

    MEASURES = ("ph", "ec", "moisture", "n", "p", "k", "om", "depth_cm")

    @property
    def recorded_at(self) -> dt.date | None:
        return self.recorded_ts.date() if self.recorded_ts else None

    @property
    def year(self) -> int | None:
        return self.recorded_ts.year if self.recorded_ts else None

    @property
    def field_key(self) -> str:
        return make_key(self.tenant, self.field_id)

    @property
    def key(self) -> str:
        return (
            f"{self.field_key}|{self.sample_id}|{_ts_iso(self.recorded_ts)}|{self.record_id or ''}"
        )

    @property
    def label(self) -> str:
        return f"{self.sample_id} ({self.year})" if self.year else self.sample_id


@dataclass
class Indicator:
    field_id: str
    indicator_id: str
    value: float | None
    recorded_ts: dt.datetime | None
    category: str | None = None
    unit: str | None = None
    status: str | None = None
    source: str | None = None
    point: tuple[float, float] | None = None
    tenant: str | None = None
    record_id: str | None = None
    qc: dict = field(default_factory=dict)
    water_kind: str | None = (
        None  # rain / et0 / kc / soil_moisture / meter / pump_hours / plan_week
    )
    conv: float | None = None  # value in the working unit of its water kind, after QC

    @property
    def recorded_at(self) -> dt.date | None:
        return self.recorded_ts.date() if self.recorded_ts else None

    @property
    def field_key(self) -> str:
        return make_key(self.tenant, self.field_id)

    @property
    def key(self) -> str:
        return f"{self.field_key}|{self.indicator_id}|{_ts_iso(self.recorded_ts)}|{self.record_id or ''}"

    def ec_dsm(self) -> float | None:
        """EC converted to dS/m, or None when the value or unit is unusable."""
        if self.value is None:
            return None
        u = self.unit_norm or "ds/m"
        if u in TDS_UNITS:
            return self.value * TDS_FACTOR
        f = EC_UNIT_FACTORS.get(u)
        return None if f is None else self.value * f

    @property
    def ec_is_approximate(self) -> bool:
        return (self.unit_norm or "") in TDS_UNITS

    @property
    def unit_norm(self) -> str | None:
        return (self.unit or "").strip().lower().replace(" ", "") or None


@dataclass
class RasterLayer:
    path: str
    index_name: str  # e.g. "SAVI"
    date: dt.date | None
    crs: str  # "EPSG:4326" or "EPSG:326xx"
    transform: tuple  # GDAL geotransform (x0, dx, rx, y0, ry, dy)
    nodata: float | None = None
    scene_id: str | None = None
    synthetic: bool = False
    role: str = "all"  # "all" | "timeline-only" (used only by season-timeline families)
    product_version: str | None = (
        None  # processing baseline / collection, for "as known then" replays
    )
    _array: object = field(default=None, repr=False)

    @property
    def key(self) -> str:
        """Location-independent identity (item ids must not depend on file paths)."""
        from pathlib import Path

        return f"{self.index_name}:{self.date}:{self.scene_id or Path(self.path).name}"

    def array(self):
        if self._array is None:
            import numpy as np

            self._array = np.load(self.path, allow_pickle=False)
        return self._array

    def pixel_sha256(self) -> str:
        if getattr(self, "_digest", None):
            return self._digest
        a = self.array()
        h = hashlib.sha256(str((a.shape, str(a.dtype))).encode())
        h.update(a.tobytes())
        self._digest = h.hexdigest()
        return self._digest


@dataclass
class FactStore:
    fields: dict[str, Field] = field(default_factory=dict)  # key = "<tenant>::<field_id>"
    soil: list[SoilSample] = field(default_factory=list)
    indicators: list[Indicator] = field(default_factory=list)
    rasters: list[RasterLayer] = field(default_factory=list)
    synthetic: bool = False
    source: str = ""
    tenant_scope: str = ""
    provenance: dict = field(default_factory=dict)
    rejected: Counter = field(default_factory=Counter)  # reason -> count of records not admitted
    boundary_tolerance_m: float = 1.0
    prepared: bool = False

    # ── admission ──
    def add_field(self, f: Field) -> bool:
        if f.key in self.fields:
            self.rejected["duplicate_field_key"] += 1
            return False
        self.fields[f.key] = f
        return True

    def inherit_tenant(self, field_id: str) -> tuple[bool, str | None]:
        """Owner tenant for a record whose source has no tenant column."""
        owners = [f for f in self.fields.values() if f.id == field_id]
        return (True, owners[0].tenant) if len(owners) == 1 else (False, None)

    def admit(self, rec) -> bool:
        """Admit a soil/indicator record only when its owner (same tenant) is loaded."""
        if rec.field_key not in self.fields:
            self.rejected["orphan_or_foreign_owner"] += 1
            return False
        (self.soil if isinstance(rec, SoilSample) else self.indicators).append(rec)
        return True

    # ── preparation (idempotent): QC, geometry quarantine, canonical order ──
    def prepare(self, rules: dict):
        if self.prepared:
            return
        self.boundary_tolerance_m = float(rules.get("boundary_tolerance_m", 1.0))
        # every timestamp is expressed in the platform's local time (Yemen: UTC+3,
        # no DST): offset-aware values are converted, naive ones are taken as
        # local. Keys and calendar days then do not depend on the DB session TimeZone.
        local = dt.timezone(dt.timedelta(hours=float(rules.get("local_utc_offset_hours", 3))))
        for rec in (*self.soil, *self.indicators):
            if rec.recorded_ts is not None:
                ts = rec.recorded_ts
                rec.recorded_ts = (
                    ts.replace(tzinfo=local) if ts.tzinfo is None else ts.astimezone(local)
                )
        lim = rules["qc_ranges"]
        for s in self.soil:
            for attr in SoilSample.MEASURES:
                v = getattr(s, attr)
                if v is None:
                    continue
                if not math.isfinite(v):
                    s.qc[attr] = {"raw": str(v), "code": "value_not_finite"}
                    setattr(s, attr, None)
                elif attr in lim and not (lim[attr][0] <= v <= lim[attr][1]):
                    s.qc[attr] = {"raw": v, "code": f"{attr}_out_of_range"}
                    setattr(s, attr, None)
        veg = rules["indicator_patterns"]["vegetation"]
        wat = rules["indicator_patterns"]["water_ec"]
        for i in self.indicators:
            if i.value is None:
                continue
            if not math.isfinite(i.value):
                i.qc["value"] = {"raw": str(i.value), "code": "value_not_finite"}
                i.value = None
            elif match_any(i.indicator_id, veg) and not (
                lim["vegetation_index"][0] <= i.value <= lim["vegetation_index"][1]
            ):
                i.qc["value"] = {"raw": i.value, "code": "index_out_of_range"}
                i.value = None
            elif match_any(i.indicator_id, wat):
                ec = i.ec_dsm()
                if ec is None:
                    i.qc["value"] = {"raw": i.value, "code": "unknown_ec_unit", "unit": i.unit}
                elif not (lim["ec"][0] <= ec <= lim["ec"][1]):
                    i.qc["value"] = {"raw": i.value, "code": "ec_out_of_range"}
                    i.value = None
        # water records: kind, unit and range. An unknown unit keeps the raw value visible
        # (an agent should see "31 kPa" and recognise it is not a volumetric content) but
        # leaves conv empty; an out-of-range value is removed like any other QC failure.
        pats = rules["indicator_patterns"]
        units, ranges = rules.get("water_units", {}), rules.get("water_ranges", {})
        for i in self.indicators:
            i.water_kind = next(
                (k for k in units if match_any(i.indicator_id, pats.get(k, []))), None
            )
            if i.water_kind is None or i.value is None:
                continue
            factor = units[i.water_kind].get(i.unit_norm or "")
            if factor is None:
                i.qc["value"] = {"raw": i.value, "code": "unknown_unit", "unit": i.unit}
                continue
            c = i.value * factor
            lo, hi = ranges.get(i.water_kind, [-math.inf, math.inf])
            if not (lo <= c <= hi):
                i.qc["value"] = {"raw": i.value, "code": "value_out_of_range"}
                i.value = None
                continue
            i.conv = c
        for f in self.fields.values():
            if f.geom is not None:
                probs = f.geom.validity_problems()
                if probs:
                    f.geom_raw, f.geom, f.geom_problems = f.geom, None, probs
                else:
                    f.geom_raw = f.geom
        self.soil.sort(key=lambda s: s.key)
        self.indicators.sort(key=lambda i: i.key)
        self.fields = dict(sorted(self.fields.items()))
        self.prepared = True

    # ── association between records and fields ──
    def _spatial(self, f: Field, point) -> bool:
        return (
            f.geom.contains(*point)
            and f.geom.boundary_distance_m(*point) >= self.boundary_tolerance_m
        )

    def samples_for(self, f: Field) -> list[tuple[SoilSample, str]]:
        """Samples of the same tenant belonging to a field.

        Field with a usable polygon: samples whose point is strictly inside it
        (ST_Contains) and at least `boundary_tolerance_m` from its boundary,
        plus same-field samples without coordinates. Field without polygon:
        same (tenant, field_id) only.
        """
        tk = tenant_key(f.tenant)
        out = []
        for s in self.soil:
            if tenant_key(s.tenant) != tk:
                continue
            if f.geom is not None and s.point is not None:
                if self._spatial(f, s.point):
                    out.append((s, "spatial"))
            elif s.field_key == f.key:
                out.append((s, "field_id"))
        return out

    def indicators_for(
        self, f: Field, patterns: list[str] | None = None
    ) -> list[tuple[Indicator, str]]:
        tk = tenant_key(f.tenant)
        out = []
        for ind in self.indicators:
            if tenant_key(ind.tenant) != tk:
                continue
            if patterns and not match_any(ind.indicator_id, patterns):
                continue
            if f.geom is not None and ind.point is not None:
                if self._spatial(f, ind.point):
                    out.append((ind, "spatial"))
            elif ind.field_key == f.key:
                out.append((ind, "field_id"))
        return out

    def drawn_fields(self) -> list[Field]:
        return [f for f in self.fields.values() if f.geom is not None]

    def unit_key(self, f: Field, unit: str) -> str:
        """Split unit a field belongs to: field | site (tenant+governorate) | governorate."""
        if unit == "field":
            return f"field:{f.key}"
        if unit == "governorate":
            return f"gov:{f.governorate or '?'}"
        return f"site:{tenant_key(f.tenant)}|{f.governorate or '?'}"


def match_any(value: str, patterns: list[str]) -> bool:
    v = value.lower()
    return any(fnmatch.fnmatch(v, p.lower().replace("%", "*")) for p in patterns)

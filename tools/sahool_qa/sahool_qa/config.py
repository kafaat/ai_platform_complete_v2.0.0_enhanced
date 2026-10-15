"""Schema mapping and agronomic rules.

Defaults match the SAHOOL v9.x init.sql schema:
  field_boundaries(field_id, field_name, area_ha, crop, soil_type,
                   latitude, longitude, governorate, tenant_id, geom)
  soil_readings(field_id, sensor_id, ph, ec_ds_m, moisture_pct, nitrogen_mg_kg,
                phosphorus_mg_kg, potassium_mg_kg, organic_matter_pct,
                depth_cm, source, recorded_at, tenant_id, geom)
  field_indicators(field_id, indicator_id, indicator_cat, value, unit, status,
                   source, recorded_at, tenant_id, geom)

Both mappings can be overridden with a JSON file (--schema-map / --rules), so a
renamed column does not require a code change.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
from pathlib import Path

DEFAULT_SCHEMA: dict = {
    "fields": {
        "table": "field_boundaries",
        "required": {"id": "field_id", "name": "field_name"},
        "optional": {
            "area_ha": "area_ha",
            "crop": "crop",
            "soil_type": "soil_type",
            "latitude": "latitude",
            "longitude": "longitude",
            "governorate": "governorate",
            "geom": "geom",
            "tenant": "tenant_id",
        },
    },
    "soil": {
        "table": "soil_readings",
        "required": {
            "field_id": "field_id",
            "sample_id": "sensor_id",
            "recorded_at": "recorded_at",
        },
        "optional": {
            "ph": "ph",
            "ec": "ec_ds_m",
            "moisture": "moisture_pct",
            "n": "nitrogen_mg_kg",
            "p": "phosphorus_mg_kg",
            "k": "potassium_mg_kg",
            "om": "organic_matter_pct",
            "depth_cm": "depth_cm",
            "source": "source",
            "geom": "geom",
            "tenant": "tenant_id",
            "record_id": "id",
        },
    },
    "indicators": {
        "table": "field_indicators",
        "required": {
            "field_id": "field_id",
            "indicator_id": "indicator_id",
            "value": "value",
            "recorded_at": "recorded_at",
        },
        "optional": {
            "category": "indicator_cat",
            "unit": "unit",
            "status": "status",
            "source": "source",
            "geom": "geom",
            "tenant": "tenant_id",
            "record_id": "id",
        },
    },
}

DEFAULT_RULES: dict = {
    # Soil salinity classes used in the SAHOOL Al-Jawf workbook (EC, dS/m).
    # Each class is [low, high) ; high = null means open-ended.
    "soil_salinity_classes": [
        {"label": "غير ملحية", "low": None, "high": 2.0},
        {"label": "ملوحة خفيفة", "low": 2.0, "high": 4.0},
        {"label": "ملوحة متوسطة", "low": 4.0, "high": 8.0},
        {"label": "ملحية", "low": 8.0, "high": None},
    ],
    # Suitability rule from the same workbook:
    #   EC>8 ضعيفة ; EC>6 حدّية ; EC>4 مناسبة بإدارة ; else مناسبة  ->  (low, high]
    "soil_suitability_classes": [
        {"label": "مناسبة", "low": None, "high": 4.0},
        {"label": "مناسبة بإدارة", "low": 4.0, "high": 6.0},
        {"label": "حدّية (تحتاج غسيلاً وصرفاً)", "low": 6.0, "high": 8.0},
        {"label": "ضعيفة (تحتاج استصلاحاً)", "low": 8.0, "high": None},
    ],
    "soil_suitability_upper_inclusive": True,
    "soil_ph_classes": [
        {"label": "حامضية", "low": None, "high": 6.5},
        {"label": "متعادلة", "low": 6.5, "high": 7.5},
        {"label": "قلوية خفيفة", "low": 7.5, "high": 8.5},
        {"label": "قلوية قوية", "low": 8.5, "high": None},
    ],
    # USSL irrigation-water salinity hazard (EC, dS/m).
    "water_salinity_classes": [
        {"label": "C1 — خطر ملوحة منخفض", "low": None, "high": 0.25},
        {"label": "C2 — خطر ملوحة متوسط", "low": 0.25, "high": 0.75},
        {"label": "C3 — خطر ملوحة عالٍ", "low": 0.75, "high": 2.25},
        {"label": "C4 — خطر ملوحة عالٍ جداً", "low": 2.25, "high": None},
    ],
    # Indicator ids (SQL LIKE patterns, lower-cased match) per meaning.
    "indicator_patterns": {
        "water_ec": ["water_ec%", "well_ec%", "ec_water%"],
        "vegetation": ["savi%", "ndvi%", "evi%", "ndwi%"],
        # water investigation (0.4.0). The text after the literal prefix names the
        # rain source (rain_mm_<source>) or the well (meter_total_<well>, pump_hours_<well>).
        "rain": ["rain_mm_%"],  # daily rainfall, mm
        "et0": ["et0_mm%"],  # daily reference ET (FAO Penman-Monteith), mm
        "kc": ["kc", "kc_%"],  # crop coefficient, holds from its date until the next record
        "soil_moisture": ["soil_moisture_vol%"],  # volumetric soil water content (probe)
        "meter": ["meter_total_%"],  # cumulative well flow meter (totalizer), m3
        "pump_hours": ["pump_hours_%"],  # cumulative pump hour meter, h
        "plan_week": [
            "irrigation_plan_week%"
        ],  # planned gross depth for the 7 days starting that date, mm
        "well_status": [
            "well_status_%"
        ],  # 1 = in service, 0 = out of service; holds until the next record
    },
    # Accepted units per water record kind (normalised: lower case, no spaces) and the
    # factor to the working unit; plausible range after conversion. Anything else is
    # flagged by QC and the questions that need it become abstentions.
    "water_units": {
        "rain": {"mm": 1.0},
        "et0": {"mm": 1.0, "mm/day": 1.0, "mm/d": 1.0},
        "kc": {"": 1.0, "-": 1.0, "index": 1.0, "ratio": 1.0},
        "soil_moisture": {"%": 0.01, "%vol": 0.01, "vol%": 0.01, "m3/m3": 1.0, "m³/m³": 1.0},
        "meter": {"m3": 1.0, "m³": 1.0},
        "pump_hours": {"h": 1.0, "hr": 1.0, "hours": 1.0},
        "plan_week": {"mm": 1.0},
        "well_status": {"": 1.0, "-": 1.0, "status": 1.0},
    },
    "water_ranges": {
        "rain": [0.0, 500.0],
        "et0": [0.0, 20.0],
        "kc": [0.0, 1.6],
        "soil_moisture": [0.0, 0.6],
        "meter": [0.0, 1e10],
        "pump_hours": [0.0, 1e7],
        "plan_week": [0.0, 500.0],
        "well_status": [0.0, 1.0],
    },
    # Vegetation index used for coverage questions and its "vegetated" threshold.
    "vegetation_threshold": {"SAVI": 0.20, "NDVI": 0.30, "EVI": 0.20, "NDWI": 0.0},
    # Index change bands for trend questions (absolute index units).
    "index_trend_bands": [0.03, 0.10],
    # EC change bands between years (relative change).
    "ec_change_bands": [0.25, 1.00],
    # Shape classification thresholds.
    "shape": {
        "circle_compactness": 0.95,
        "rect_fill": 0.90,
        "strip_fill": 0.85,
        "strip_aspect": 4.0,
    },
    # Skip numeric-bin questions whose value sits within this relative distance
    # of a bin edge (protects against spheroid/rounding disagreement).
    "edge_margin_rel": 0.02,
    # Probability that an answerable question also offers the abstain option.
    "abstain_option_rate": 0.35,
    # Leaching / comparison questions need this relative margin between #1 and #2.
    "comparison_margin_rel": 0.10,
    # Minimum samples per field-year for aggregate questions.
    "min_samples_aggregate": 2,
    # Yemen bounding box used for coordinate sanity checks (incl. Socotra).
    "country_bbox": [41.6, 12.0, 54.8, 19.2],
    # Plausible measurement ranges. Values outside are removed from use (QC)
    # and questions about them become abstentions; the audit lists them.
    "qc_ranges": {
        "ph": [3.0, 11.0],
        "ec": [0.0, 100.0],
        "moisture": [0.0, 100.0],
        "om": [0.0, 100.0],
        "n": [0.0, 20000.0],
        "p": [0.0, 20000.0],
        "k": [0.0, 20000.0],
        "depth_cm": [0.0, 500.0],
        "vegetation_index": [-1.0, 1.0],
    },
    # Points closer than this to a field boundary are ambiguous (GPS error) and
    # are not associated spatially with that field; the audit reports them.
    "boundary_tolerance_m": 1.0,
    # Local time used for calendar days of timestamped records (Yemen: UTC+3, no DST).
    "local_utc_offset_hours": 3,
    # Season investigator — spatial pattern of weakness inside a pivot (pixel shares,
    # weakness = index below the vegetation threshold). Ring: one radial band is
    # >= anomaly_deficit below the field while sectors stay within uniform_tol of
    # each other; sector: the mirror case; field-wide / none: everything within
    # uniform_tol and the field share low / high. Cases within `margin` of any
    # threshold are not asked.
    "pattern": {
        "n_rings": 5,
        "anomaly_deficit": 0.25,
        "uniform_tol": 0.12,
        "healthy_min": 0.80,
        "fieldwide_max": 0.50,
        "margin": 0.03,
        "min_valid_frac": 0.95,
        "min_bin_pixels": 30,
    },
    # Divergence onset: a scene counts only if >= min_field_valid of the field and
    # >= min_sector_valid of the sector are valid; a divergence is reliable when the
    # sector is >= deficit below the rest of the field in `persist` consecutive valid scenes.
    "divergence": {
        "deficit": 0.25,
        "persist": 2,
        "min_field_valid": 0.90,
        "min_sector_valid": 0.80,
        "margin": 0.03,
        "min_scenes": 4,
        "max_gap_days": 60,
    },
    # Green-up: first observation at or above the vegetation threshold that is
    # followed by another one (two consecutive daily values).
    "green_up": {"min_points": 5, "margin": 0.01},
    # ── Water investigation (0.4.0). Values marked FAO are from FAO Irrigation and Drainage
    # Paper 56; everything else is a SAHOOL assumption to be reviewed by an agronomist.
    "water": {
        # Complete well assignments, keyed by tenant::field. Dates inclusive; suffixes case-insensitive.
        # Fixture provenance may supply this same explicit contract. Missing inventory is unknown.
        "well_inventory": {},
        # FAO-56 Table 19 (chapter 7): typical θFC and θWP ranges, m3/m3, by USDA texture.
        # The balance uses the midpoint of each range.
        "soil_water": {
            "sand": {"fc": [0.07, 0.17], "wp": [0.02, 0.07]},
            "loamy_sand": {"fc": [0.11, 0.19], "wp": [0.03, 0.10]},
            "sandy_loam": {"fc": [0.18, 0.28], "wp": [0.06, 0.16]},
            "loam": {"fc": [0.20, 0.30], "wp": [0.07, 0.17]},
            "silt_loam": {"fc": [0.22, 0.36], "wp": [0.09, 0.21]},
            "silt": {"fc": [0.28, 0.36], "wp": [0.12, 0.22]},
            "silty_clay_loam": {"fc": [0.30, 0.37], "wp": [0.17, 0.24]},
            "silty_clay": {"fc": [0.30, 0.42], "wp": [0.17, 0.29]},
            "clay": {"fc": [0.32, 0.40], "wp": [0.20, 0.24]},
        },
        # FAO-56 Table 22 (chapter 8): maximum effective rooting depth range (m) and the
        # depletion fraction p at ETc ≈ 5 mm/day, keyed by the crop name stored in field_boundaries.
        "crops": {
            "قمح": {"zr": [1.0, 1.5], "p": 0.55, "fao": "Wheat, spring"},
            "شعير": {"zr": [1.0, 1.5], "p": 0.55, "fao": "Barley"},
            "ذرة رفيعة": {"zr": [1.0, 2.0], "p": 0.55, "fao": "Sorghum, grain"},
            "ذرة شامية": {"zr": [1.0, 1.7], "p": 0.55, "fao": "Maize, field (grain)"},
            "دخن": {"zr": [1.0, 2.0], "p": 0.55, "fao": "Millet"},
            "برسيم": {"zr": [1.0, 2.0], "p": 0.55, "fao": "Alfalfa, for hay"},
            "نخيل": {"zr": [1.5, 2.5], "p": 0.50, "fao": "Date palms"},
            "طماطم": {"zr": [0.7, 1.5], "p": 0.40, "fao": "Tomato"},
            "بطاطس": {"zr": [0.4, 0.6], "p": 0.35, "fao": "Potato"},
            "قطن": {"zr": [1.0, 1.7], "p": 0.65, "fao": "Cotton"},
            "سمسم": {"zr": [1.0, 1.5], "p": 0.60, "fao": "Sesame"},
            "عنب": {"zr": [1.0, 2.0], "p": 0.35, "fao": "Grapes, table or raisin"},
        },
        # FAO-56 Table 22 note: the smaller Zr values may be used for irrigation scheduling.
        "zr_choice": "low",
        # Assumption: share of the gross metered volume that is stored in the root zone.
        "application_efficiency": 0.80,
        # The balance assumes runoff RO = 0 and capillary rise CR = 0 (FAO-56 ch. 8 allows
        # CR = 0 when the water table is > ~1 m below the root zone). Days with more rain
        # than this make RO = 0 unsafe, so those balances are not asked.
        "runoff_free_max_mm": 20.0,
        "check_every_days": 7,  # stress questions every N days after a moisture reading
        "stress_margin_mm": 3.0,  # |Dr - RAW| below this is not asked
        "ks_severe": 0.5,
        "ks_margin": 0.05,
        "depth_rel_width": 0.20,
        "depth_min_width_mm": 2.0,
        "plan_tolerance_rel": 0.10,
        "plan_margin_rel": 0.02,
        # Rain corroboration: an event (>= event_mm on one day in one source) is confirmed when
        # a source with an independent lineage, complete over ±window_days, sums >= confirm_mm.
        "rain_event_mm": 5.0,
        "rain_confirm_mm": 2.0,
        "rain_window_days": 1,
        "rain_margin_mm": 0.5,
        # Source lineage: two sources are independent only when these sets do not intersect.
        # CHIRPS v3 daily ("rnl") takes its daily split from ERA5, and ERA5-Land precipitation
        # is the ERA5 forcing, so on a given day the two are not independent of each other.
        "rain_sources": {
            "station": {"label": "مقياس مطر المزرعة", "lineage": ["gauge"]},
            "chirps_v3_rnl": {
                "label": "CHIRPS v3 اليومي (التوزيع اليومي من ERA5)",
                "lineage": ["era5"],
            },
            "era5land": {"label": "ERA5-Land", "lineage": ["era5"]},
        },
        "rain_priority": ["station", "chirps_v3_rnl", "era5land"],  # source used by the balance
        "min_refill_deficit_mm": 5.0,
        "max_pump_hours_per_day": 10.0,  # assumption: hours a well may run per day
        "flow_window_days": 7,  # well flow = Δ meter / Δ pump hours over this window
        # Hour meter advanced by at least this much while the volume meter of the same well did not:
        # the two instruments disagree (stuck meter, dry well or closed valve cannot be told apart).
        "stall_min_hours": 1.0,
        "refill_days": [2.0, 5.0],
        "refill_margin_rel": 0.10,
    },
}

ABSTAIN_TEXT = "لا تتوفر في المنصة بيانات كافية وموثوقة للإجابة"

# What the answer rests on (REA's observed / derived / inferred split):
#   observed — read directly from a record (crop, a lab value);
#   derived  — computed from records by a stated rule (area, class, mean, pixel share);
#   inferred — a hypothesis or recommendation that still needs field confirmation.
EVIDENCE_KINDS = {"observed": "مرصود", "derived": "مشتق", "inferred": "مستنتج"}

LEVELS = {
    "spatial_perception": "الإدراك المكاني",
    "object_understanding": "فهم الهدف",
    "scene_understanding": "فهم المشهد",
    "scene_reasoning": "الاستدلال",
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_schema(path: str | None) -> dict:
    if not path:
        return copy.deepcopy(DEFAULT_SCHEMA)
    return _deep_merge(DEFAULT_SCHEMA, json.loads(Path(path).read_text(encoding="utf-8")))


def load_rules(path: str | None) -> dict:
    if not path:
        return copy.deepcopy(DEFAULT_RULES)
    return _deep_merge(DEFAULT_RULES, json.loads(Path(path).read_text(encoding="utf-8")))


def classify(value: float, classes: list[dict], upper_inclusive: bool = False) -> str:
    """Return the label of the class containing value.

    Default intervals are [low, high). With upper_inclusive the intervals are
    (low, high], matching Excel rules written as IF(x>8, ...).
    """
    for c in classes:
        lo, hi = c["low"], c["high"]
        if upper_inclusive:
            if (lo is None or value > lo) and (hi is None or value <= hi):
                return c["label"]
        else:
            if (lo is None or value >= lo) and (hi is None or value < hi):
                return c["label"]
    raise ValueError(f"value {value} not covered by classes")


def describe_classes(classes: list[dict], unit: str, upper_inclusive: bool = False) -> str:
    """Arabic one-line description of the thresholds, for evidence records."""
    parts = []
    for c in classes:
        lo, hi = c["low"], c["high"]
        if lo is None:
            rng = f"≤ {hi}" if upper_inclusive else f"< {hi}"
        elif hi is None:
            rng = f"> {lo}" if upper_inclusive else f"≥ {lo}"
        else:
            rng = f"> {lo} و ≤ {hi}" if upper_inclusive else f"≥ {lo} و < {hi}"
        parts.append(f"{c['label']}: {rng} {unit}")
    return "؛ ".join(parts)


def validate_water_rules(rules: dict):
    w = rules["water"]
    for key in ("application_efficiency", "max_pump_hours_per_day"):
        v = w[key]
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"water.{key} must be finite and positive")
    if w["application_efficiency"] > 1 or w["max_pump_hours_per_day"] > 24:
        raise ValueError("Ea must be <= 1 and daily pump hours <= 24")
    for key in ("flow_window_days", "check_every_days"):
        if isinstance(w[key], bool) or not isinstance(w[key], int) or w[key] < 1:
            raise ValueError(f"water.{key} must be a positive integer")
    lo, hi = w["refill_days"]
    if (
        not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (lo, hi))
        or not 0 < lo < hi
    ):
        raise ValueError("refill_days must be finite increasing positive thresholds")
    for key, periods in w.get("well_inventory", {}).items():
        if "::" not in key or not isinstance(periods, list):
            raise ValueError("well_inventory requires tenant::field keys and period lists")
        last = None
        for v in sorted(periods, key=lambda x: x["from"]):
            a, b = dt.date.fromisoformat(v["from"]), dt.date.fromisoformat(v["to"])
            if b < a or (last is not None and a <= last):
                raise ValueError("overlapping or reversed well inventory dates")
            if not isinstance(v["wells"], list) or any(
                not isinstance(x, str) or not x for x in v["wells"]
            ):
                raise ValueError("inventory wells must be non-empty string suffixes")
            if len({x.lower() for x in v["wells"]}) != len(v["wells"]):
                raise ValueError("duplicate wells in inventory")
            last = b

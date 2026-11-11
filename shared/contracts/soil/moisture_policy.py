"""Soil-moisture decision eligibility — one rule for every consumer (`SOIL-MOISTURE-ELIGIBILITY-01`).

**Why this exists.** On ``8216ef41d`` the same reading was judged four ways:
``soil_telemetry.irrigation_soil_input`` used any fresh non-VWC reading with no quality
check (so an ``uncalibrated`` bare ``%`` could make irrigation "high"); the alerts path
passed ``value_pct`` raw with no age or quality check; ``weather_advice`` read an
undeclared unit as available water; and the profile composer ranked confidence before
recency and let an uncalibrated sensor beat an accepted field reading. Every consumer
now asks this module instead of re-deriving its own rule.

**The rule (``POLICY_VERSION``):**

- ``superseded`` or ``quality_status == "rejected"`` ⇒ **excluded** (not shown as current).
- The measurement is **current** only when ``quality_status == "accepted"`` *and* its age
  is proven within ``max_age_s`` (``fresh``; missing/invalid ⇒ ``unproven``, a timestamp
  beyond the skew tolerance ⇒ ``future``). ``uncalibrated``/``suspect``/absent quality or a
  non-fresh age ⇒ **advisory**: it may be displayed, never decided on.
- Only a current reading whose unit is **declared available water** is comparable to the
  30 %/60 % available-water thresholds ⇒ ``decision_eligible`` / ``may_raise_urgency``.
  ``vwc_pct`` needs θFC/θWP to convert, which the advice/alert paths do not have; a bare or
  undeclared ``%`` says nothing about which percentage it is ⇒ advisory.
- ``may_seed`` (water-twin initial depletion) needs a current reading with a **declared**
  unit (``available_pct`` or ``vwc_pct``); the seeder itself converts VWC with θFC/Zr.

Advisory readings must never *raise* irrigation urgency; consumers keep them out of the
decision entirely (neither raise nor lower), and surface the ``limitations`` instead.

Pure (stdlib only, no I/O) so every service imports it without new dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

POLICY_VERSION = "soil-moisture-eligibility.v1"

#: Sensor TTL: hourly reporting, four missed reports ⇒ stale. This is the single source —
#: ``sahool-platform/api/device_registry.py`` declares ``soil_moisture_sensor.max_reading_age_s``
#: from this constant, and the soil profile composer uses it for dynamic properties.
SOIL_MOISTURE_SENSOR_TTL_S = 4 * 3600

#: Dynamic soil properties (they change within hours) share the sensor TTL.
DYNAMIC_PROPERTY_TTL_S = SOIL_MOISTURE_SENSOR_TTL_S

#: Clock skew up to five minutes counts as fresh; further ahead is a future timestamp.
FUTURE_SKEW_TOLERANCE_S = 300.0

#: Water-ledger (daily bucket) age beyond which the latest row is not current state. The
#: platform's ``api/irrigation_state_guard.DEFAULT_MAX_LEDGER_AGE_HOURS`` is this value, and
#: every ledger consumer (canonical water state, water twin, field-state water stress)
#: imports it from there.
WATER_LEDGER_MAX_AGE_HOURS = 72.0

# ── Field-operation advice on MODELLED surface moisture ──────────────────────────────
#: These thresholds apply to the weather model's surface layer (Open-Meteo
#: ``soil_moisture_1_to_3cm``, m³/m³) — a modelled value, not a sensor reading and not
#: root-zone available water, so none of the eligibility rules above apply to it. Both
#: ``sahool-platform/api/routers/weather.py::_operation_suitability`` and
#: ``weather-service/operations.py::operation_suitability`` read them from here (a parity
#: test pins it); before, sowing said "dry" below 0.18 in one service and 0.12 in the other.
#:
#: DRY 0.18 = FAO-56 Table 19 θFC of sandy loam: a surface layer below it is drier than field
#: capacity of light (sandy-loam) soils ⇒ sowing penalised,
#: irrigation need flagged. WET 0.34 ⇒ surface near saturation for loams ⇒ harvest
#: trafficability penalised / irrigation pointless. Advisory field-ops heuristics, not
#: calibrated per field.
MODELLED_SURFACE_MOISTURE_SOURCE = "modelled_surface_soil_moisture_1_to_3cm"
SURFACE_MOISTURE_DRY_M3M3 = 0.18
SURFACE_MOISTURE_WET_M3M3 = 0.34

UNIT_AVAILABLE_PCT = "available_pct"
UNIT_VWC_PCT = "vwc_pct"
UNIT_UNDECLARED = "undeclared"

QUALITY_ACCEPTED = "accepted"
QUALITY_UNCALIBRATED = "uncalibrated"
QUALITY_SUSPECT = "suspect"
QUALITY_REJECTED = "rejected"

#: Only ``accepted`` qualifies for decisions or seeding; absence is not acceptance.
DECISION_ELIGIBLE_QUALITY_STATUSES = frozenset({QUALITY_ACCEPTED})

#: Quality as a ranking tier (higher wins). ``rejected`` is excluded, not ranked.
QUALITY_TIER = {QUALITY_ACCEPTED: 3, QUALITY_UNCALIBRATED: 2, QUALITY_SUSPECT: 1}

FRESH = "fresh"
STALE = "stale"
UNPROVEN = "unproven"
FUTURE = "future"

LIMIT_SENSOR_STALE = "soil_moisture_sensor_reading_stale"
LIMIT_FRESHNESS_UNPROVEN = "soil_moisture_sensor_freshness_unproven"
LIMIT_TIMESTAMP_IN_FUTURE = "soil_moisture_sensor_timestamp_in_future"
LIMIT_VWC_NOT_COMPARABLE = "soil_moisture_vwc_not_comparable_to_available_water"
LIMIT_UNIT_UNDECLARED = "soil_moisture_sensor_unit_undeclared"
LIMIT_QUALITY_UNPROVEN = "soil_moisture_sensor_quality_unproven"
LIMIT_QUALITY_NOT_DECISION_ELIGIBLE = "soil_moisture_sensor_quality_not_decision_eligible"
LIMIT_QUALITY_REJECTED = "soil_moisture_sensor_quality_rejected"
LIMIT_SUPERSEDED = "soil_moisture_observation_superseded"

FRESHNESS_LIMITATION = {
    STALE: LIMIT_SENSOR_STALE,
    UNPROVEN: LIMIT_FRESHNESS_UNPROVEN,
    FUTURE: LIMIT_TIMESTAMP_IN_FUTURE,
}


def _finite(value: float | None) -> bool:
    return (
        value is not None
        and not isinstance(value, bool)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def classify_freshness(age_s: float | None, max_age_s: float | None) -> str:
    """Freshness is positive proof: ``fresh`` only for a finite age within a positive TTL."""
    if not _finite(age_s) or not _finite(max_age_s) or float(max_age_s) <= 0:
        return UNPROVEN
    if float(age_s) < -FUTURE_SKEW_TOLERANCE_S:
        return FUTURE
    if float(age_s) > float(max_age_s):
        return STALE
    return FRESH


def _aware(value: datetime) -> datetime:
    # timestamptz arrives aware; a naive value is treated as UTC explicitly.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def reading_age_s(observed_at: datetime | None, now: datetime) -> float | None:
    """Seconds between ``observed_at`` and ``now``; ``None`` when there is no timestamp."""
    if not isinstance(observed_at, datetime):
        return None
    return (_aware(now) - _aware(observed_at)).total_seconds()


def normalize_quality(quality_status: object) -> str | None:
    if quality_status is None:
        return None
    text = str(getattr(quality_status, "value", quality_status)).strip().lower()
    return text or None


def quality_tier(quality_status: object) -> int:
    """Ranking tier: accepted 3 > uncalibrated 2 > suspect 1 > unknown/absent 0."""
    return QUALITY_TIER.get(normalize_quality(quality_status) or "", 0)


@dataclass(frozen=True)
class MoistureEligibility:
    """What a consumer may do with one soil-moisture reading, and why not."""

    decision_eligible: bool
    may_raise_urgency: bool
    may_seed: bool
    #: accepted quality + proven-fresh age (unit-agnostic): the measurement itself is current.
    measurement_current: bool
    #: rejected or superseded — not to be presented as current evidence at all.
    excluded: bool
    freshness: str
    limitations: tuple[str, ...]
    policy_version: str = POLICY_VERSION

    @property
    def advisory(self) -> bool:
        """Shown with its limitations, never decided on."""
        return not self.excluded and not self.decision_eligible


def moisture_eligibility(
    unit_kind: str | None,
    quality_status: object,
    observed_at: datetime | None,
    now: datetime,
    superseded: bool = False,
    *,
    max_age_s: float | None = SOIL_MOISTURE_SENSOR_TTL_S,
) -> MoistureEligibility:
    """Apply the shared rule to one reading (see the module docstring)."""
    freshness = classify_freshness(reading_age_s(observed_at, now), max_age_s)
    quality = normalize_quality(quality_status)
    limitations: list[str] = []
    excluded = False
    if superseded:
        limitations.append(LIMIT_SUPERSEDED)
        excluded = True
    if quality == QUALITY_REJECTED:
        limitations.append(LIMIT_QUALITY_REJECTED)
        excluded = True
    if freshness != FRESH:
        limitations.append(FRESHNESS_LIMITATION[freshness])
    kind = unit_kind or UNIT_UNDECLARED
    if kind == UNIT_VWC_PCT:
        limitations.append(LIMIT_VWC_NOT_COMPARABLE)
    elif kind != UNIT_AVAILABLE_PCT:
        limitations.append(LIMIT_UNIT_UNDECLARED)
    if quality is None:
        limitations.append(LIMIT_QUALITY_UNPROVEN)
    elif quality not in DECISION_ELIGIBLE_QUALITY_STATUSES and quality != QUALITY_REJECTED:
        limitations.append(f"{LIMIT_QUALITY_NOT_DECISION_ELIGIBLE}:{quality}")

    current = not excluded and freshness == FRESH and quality in DECISION_ELIGIBLE_QUALITY_STATUSES
    decision = current and kind == UNIT_AVAILABLE_PCT
    return MoistureEligibility(
        decision_eligible=decision,
        may_raise_urgency=decision,
        may_seed=current and kind in (UNIT_AVAILABLE_PCT, UNIT_VWC_PCT),
        measurement_current=current,
        excluded=excluded,
        freshness=freshness,
        limitations=tuple(limitations),
    )

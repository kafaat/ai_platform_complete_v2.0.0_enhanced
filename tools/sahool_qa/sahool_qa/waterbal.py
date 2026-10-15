"""Water investigation core (0.4.0): daily series from field_indicators,
cumulative-meter differences, and the FAO-56 chapter 8 root-zone balance.
Pure functions; the generator and the audit both use them.

Contract — a missing record is never a zero:
* a day without a usable record of a daily quantity (rain, ET0) makes any sum
  or balance over that day unknown;
* a cumulative meter (flow totalizer, pump hours) needs readings only at the
  two ends of a window — the total in between is known even across gaps —
  but the daily split inside a gap is not, so the daily balance needs a
  reading on every day;
* a meter reading lower than the one before it (reset or replacement) makes
  the volume across it unknown;
* a field with no meter has unknown irrigation, not zero irrigation;
* a meter recorded under two fields cannot be split between them.

FAO-56 balance (eqs 82-88), daily, from the end of the day of a soil-moisture reading:
    TAW = 1000 (θFC - θWP) Zr            RAW = p TAW
    p   = p_table + 0.04 (5 - ETc)  clipped to [0.1, 0.8]
    Ks  = 1 if Dr ≤ RAW else (TAW - Dr) / ((1 - p) TAW)       (Dr at the start of the day)
    ET_actual = min(Ks·Kc·ET0_i, max(0, TAW - Dr,i-1 + P_i + Ea·I_gross,i))
    Dr,i = Dr,i-1 - P_i - Ea·I_gross,i + ET_actual, clipped to [0, TAW]; water above
           field capacity leaves as deep percolation. RO = 0 and CR = 0 are assumed.
    Dr,0 = 1000 (θFC - θ0) Zr  clipped to [0, TAW]   (eq 87)
"""
from __future__ import annotations

import datetime as dt
import statistics
import math
from dataclasses import dataclass, field

from .facts import FactStore, Field, Indicator, tenant_key

KINDS = ("rain", "et0", "kc", "soil_moisture", "meter", "pump_hours", "plan_week", "well_status")
STEP_KINDS = ("kc", "plan_week", "well_status")      # records that hold until the next one
TOTALIZERS = ("meter", "pump_hours")
DAY = dt.timedelta(days=1)


def days_between(a: dt.date, b: dt.date) -> list[dt.date]:
    """a..b inclusive."""
    return [a + DAY * k for k in range((b - a).days + 1)]


def suffix(indicator_id: str, patterns: list[str]) -> str:
    """'rain_mm_station' -> 'station', 'meter_total_W-P1' -> 'w-p1' (lower case)."""
    v = indicator_id.lower()
    for p in patterns:
        if "%" in p:
            pre = p.lower().split("%")[0]
            if v.startswith(pre) and len(v) > len(pre):
                return v[len(pre):]
    return v


@dataclass
class Series:
    """One indicator id for one field, by local calendar day (records include QC-rejected ones)."""
    kind: str
    indicator_id: str
    records: dict = field(default_factory=dict)        # date -> [Indicator]

    def value(self, d: dt.date) -> float | None:
        """Usable value of a day, or None. Daily quantities: mean of the day's usable records;
        cumulative meters: the latest usable reading of the day."""
        recs = [r for r in self.records.get(d, []) if r.conv is not None]
        if not recs:
            return None
        if self.kind in TOTALIZERS:
            return max(recs, key=lambda r: (r.recorded_ts, r.key)).conv
        return statistics.fmean(r.conv for r in recs)

    def days(self) -> list[dt.date]:
        return sorted(self.records)

    def usable_days(self) -> list[dt.date]:
        return [d for d in self.days() if self.value(d) is not None]

    def between(self, a: dt.date, b: dt.date) -> list[Indicator]:
        return [r for d in self.days() if a <= d <= b for r in self.records[d]]

    @property
    def unit(self) -> str:
        units = [r.unit or "" for rs in self.records.values() for r in rs]
        return max(sorted(set(units)), key=units.count) if units else ""

    @property
    def source(self) -> str:
        src = [r.source or "" for rs in self.records.values() for r in rs]
        return max(sorted(set(src)), key=src.count) if src else ""

    def ref(self, a: dt.date | None = None, b: dt.date | None = None) -> dict:
        recs = self.between(a, b) if a and b else [r for rs in self.records.values() for r in rs]
        f0 = recs[0] if recs else None
        return {"table": "field_indicators", "field_key": f0.field_key if f0 else None,
                "field_id": f0.field_id if f0 else None, "indicator_id": self.indicator_id,
                "from": str(a) if a else str(self.days()[0]), "to": str(b) if b else str(self.days()[-1]),
                "n_records": len(recs)}


@dataclass
class FieldWater:
    field: Field
    series: dict                                         # kind -> {suffix: Series}

    def of(self, kind: str) -> dict:
        return self.series.get(kind, {})

    def all_days(self) -> list[dt.date]:
        """Days of the daily series. Kc and plan records are left out: a Kc record often
        precedes the window it applies to, and a plan week runs past its record date."""
        return sorted({d for k in KINDS if k not in STEP_KINDS for s in self.of(k).values() for d in s.records})

    def has_any(self) -> bool:
        return any(self.of(k) for k in KINDS)


def field_water(store: FactStore, f: Field, rules: dict) -> FieldWater:
    pats = rules["indicator_patterns"]
    allp = [p for k in KINDS for p in pats.get(k, [])]
    out: dict = {k: {} for k in KINDS}
    for ind, _ in store.indicators_for(f, allp):
        if ind.water_kind is None or ind.recorded_ts is None:
            continue
        sx = suffix(ind.indicator_id, pats[ind.water_kind])
        s = out[ind.water_kind].setdefault(sx, Series(ind.water_kind, ind.indicator_id))
        s.records.setdefault(ind.recorded_at, []).append(ind)
    for k in KINDS:
        for s in out[k].values():
            for d in s.records:
                s.records[d].sort(key=lambda r: r.key)
        out[k] = dict(sorted(out[k].items()))
    return FieldWater(f, out)


def meter_owners(store: FactStore, rules: dict) -> dict:
    """(tenant, meter indicator id) -> sorted field keys whose records carry it."""
    owners: dict = {}
    for f in store.fields.values():
        for s in field_water(store, f, rules).of("meter").values():
            owners.setdefault((tenant_key(f.tenant), s.indicator_id), set()).add(f.key)
    return {k: sorted(v) for k, v in owners.items()}


# ───────────────────────── cumulative meters ─────────────────────────

def meter_records(s: Series, a: dt.date, b: dt.date) -> list[Indicator]:
    """Raw usable readings between the selected end-of-day endpoints, inclusive.
    A reset before the starting endpoint or after the ending endpoint is irrelevant.
    """
    def endpoint(day):
        rows = [r for r in s.records.get(day, []) if r.conv is not None]
        return max(rows, key=lambda r: (r.recorded_ts, r.key)) if rows else None
    first, last = endpoint(a), endpoint(b)
    if first is None or last is None:
        return []
    return sorted((r for r in s.between(a, b) if r.conv is not None
                   and first.recorded_ts <= r.recorded_ts <= last.recorded_ts),
                  key=lambda r: (r.recorded_ts, r.key))


def meter_sequence_problem(rows: list[Indicator]) -> str | None:
    for x, y in zip(rows, rows[1:]):
        if x.recorded_ts == y.recorded_ts and x.conv != y.conv:
            return "meter_timestamp_conflict"
        if y.conv < x.conv:
            return "meter_decrease"
    return None


def inventory_for(store: FactStore, f: Field, rules: dict):
    """Explicit, tenant-qualified, complete well assignments; never infer from meters."""
    configured = rules["water"].get("well_inventory", {})
    if f.key in configured:
        return configured[f.key]
    return store.provenance.get("water_well_inventory", {}).get(f.key)


def coverage_problem(store: FactStore, fw: FieldWater, rules: dict, a: dt.date, b: dt.date):
    inventory = inventory_for(store, fw.field, rules)
    present = set(fw.of("meter"))
    # Even without an inventory, a pump-hours stream without a volume stream is a known gap.
    missing = set(fw.of("pump_hours")) - present
    if missing:
        return "missing_expected_meter", sorted(missing)
    if inventory is None:
        return "well_inventory_missing", fw.field.key
    expected = None
    for day in days_between(a, b):
        active = [v for v in inventory if dt.date.fromisoformat(v["from"]) <= day <= dt.date.fromisoformat(v["to"])]
        if len(active) != 1:
            return "well_inventory_gap", str(day)
        wells = {x.lower() for x in active[0]["wells"]}
        if expected is not None and wells != expected:
            return "well_assignment_changed", str(day)
        expected = wells
    if expected - present:
        return "missing_expected_meter", sorted(expected - present)
    if present - expected:
        return "unassigned_meter", sorted(present - expected)
    return None, None


def window_delta(s: Series, a: dt.date, b: dt.date) -> tuple[float | None, str | None]:
    """Total between the readings of day a and day b. Gaps in between are harmless; a
    missing end reading or a decrease anywhere in [a, b] makes it unknown."""
    va, vb = s.value(a), s.value(b)
    if va is None or vb is None:
        return None, "missing_endpoint"
    problem = meter_sequence_problem(meter_records(s, a, b))
    if problem:
        return None, problem
    return vb - va, None


def naive_delta(s: Series, a: dt.date, b: dt.date) -> float:
    """What a reader who ignores gaps and resets would report: the sum of the non-negative
    steps between the usable readings that do exist in [a, b]."""
    vals = [s.value(d) for d in s.usable_days() if a <= d <= b]
    return sum(max(0.0, y - x) for x, y in zip(vals, vals[1:]))


def daily_increments(s: Series, a: dt.date, b: dt.date) -> tuple[dict | None, str | None, dt.date | None]:
    """{day: volume between the reading of day-1 and of day} for a < day <= b."""
    prev = s.value(a)
    if prev is None:
        return None, "missing_daily_reading", a
    out = {}
    for d in days_between(a + DAY, b):
        cur = s.value(d)
        if cur is None:
            return None, "missing_daily_reading", d
        problem = meter_sequence_problem(meter_records(s, d - DAY, d))
        if problem:
            return None, problem, d
        out[d] = cur - prev
        prev = cur
    return out, None, None


# ───────────────────────── parameters and balance ─────────────────────────

def norm_soil(s: str | None) -> str | None:
    if not s:
        return None
    return "_".join(str(s).strip().lower().replace("-", " ").split())


def field_params(f: Field, rules: dict) -> tuple[dict | None, str | None]:
    w = rules["water"]
    soil = norm_soil(f.soil_type)
    if soil is None:
        return None, "soil_type_missing"
    if soil not in w["soil_water"]:
        return None, "soil_type_not_in_rules"
    crop = (f.crop or "").strip()
    if not crop:
        return None, "crop_missing"
    if crop not in w["crops"]:
        return None, "crop_not_in_rules"
    sw, cp = w["soil_water"][soil], w["crops"][crop]
    fc, wp = round(sum(sw["fc"]) / 2, 4), round(sum(sw["wp"]) / 2, 4)
    zr = {"low": cp["zr"][0], "high": cp["zr"][1]}.get(w.get("zr_choice", "low"), round(sum(cp["zr"]) / 2, 3))
    taw = 1000 * (fc - wp) * zr
    return {"soil": soil, "crop": crop, "fao_crop": cp.get("fao"), "fc": fc, "wp": wp, "zr": zr,
            "p_table": cp["p"], "ea": w["application_efficiency"], "taw": round(taw, 4)}, None


def p_adjusted(p_table: float, etc: float) -> float:
    return min(0.8, max(0.1, p_table + 0.04 * (5.0 - etc)))


def ks_of(dr: float, taw: float, p: float) -> float:
    raw = p * taw
    return 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - p) * taw))


def balance(prm: dict, theta0: float, days: list[dt.date], et0: dict, kc: dict, rain: dict,
            irr_gross: dict) -> tuple[float, list[dict]]:
    taw, ea = prm["taw"], prm["ea"]
    if not all(math.isfinite(prm[k]) for k in ("fc", "wp", "zr", "taw", "ea", "p_table")) or not (
            prm["fc"] > prm["wp"] >= 0 and prm["zr"] > 0 and taw > 0 and 0 < ea <= 1):
        raise ValueError("invalid root-zone parameters")
    dr = min(max(1000 * (prm["fc"] - theta0) * prm["zr"], 0.0), taw)
    dr0 = dr
    rows = []
    for d in days:
        etc = kc[d] * et0[d]
        p = p_adjusted(prm["p_table"], etc)
        ks = ks_of(dr, taw, p)
        inet = irr_gross[d] * ea
        # Extraction cannot exceed water available above WP. Clipping only Dr breaks eq. 85.
        eta_potential = ks * etc
        eta = min(eta_potential, max(0.0, taw - dr + rain[d] + inet))
        x = dr - rain[d] - inet + eta
        dp = max(0.0, -x)
        dr = min(max(x, 0.0), taw)
        rows.append({"date": str(d), "et0": et0[d], "kc": kc[d], "etc": etc, "p": p, "raw": p * taw,
                     "ks_start": ks, "eta": eta, "eta_unlimited": eta_potential, "rain": rain[d], "irr_gross": irr_gross[d], "irr_net": inet,
                     "dp": dp, "dr_end": dr})
    return dr0, rows


def step_value(series: Series, d: dt.date) -> float | None:
    """A step record (Kc, well status) holds from its date until the next record; a rejected
    latest record is unknown, and so is a day before the first record."""
    past = [x for x in series.days() if x <= d]
    return series.value(past[-1]) if past else None


kc_on = step_value


# ───────────────────────── well status and the two meters of a well ─────────────────────────

def out_of_service(fw: "FieldWater", well: str, a: dt.date, b: dt.date) -> bool:
    """True only when a well_status record in force says 0 on every pumping day a+1..b."""
    s = fw.of("well_status").get(well)
    days = days_between(a + DAY, b)
    return s is not None and bool(days) and all(step_value(s, d) == 0 for d in days)


def instrument_problem(fw: "FieldWater", well: str, a: dt.date, b: dt.date, rules: dict) -> tuple[str | None, str | None]:
    """Compare the volume meter and the hour meter of one well between consecutive end-of-day
    readings that both exist in [a, b].

    volume_meter_stalled — hours advanced (>= stall_min_hours) while the volume did not, and no
        status record says the well was out of service then: a stuck meter, a dry well and a
        closed valve look the same, so the volume (and the flow) is unknown, never zero.
    hour_meter_stalled   — volume advanced while hours did not: the flow is unknown; the volume
        itself is still the direct measurement.
    well_status_conflict — volume advanced while a status record says out of service.
    """
    ms, hs = fw.of("meter").get(well), fw.of("pump_hours").get(well)
    if ms is None:
        return None, None
    min_h = rules["water"].get("stall_min_hours", 1.0)
    days = [d for d in days_between(a, b) if ms.value(d) is not None]
    for x, y in zip(days, days[1:]):
        dv = ms.value(y) - ms.value(x)
        if dv > 0 and out_of_service(fw, well, x, y):
            return "well_status_conflict", f"{well} {x}..{y}"
    if hs is None:
        return None, None
    days = [d for d in days if hs.value(d) is not None]
    for x, y in zip(days, days[1:]):
        dv, dh = ms.value(y) - ms.value(x), hs.value(y) - hs.value(x)
        if dh >= min_h and dv == 0 and not out_of_service(fw, well, x, y):     # a drop is a reset, not a stall
            return "volume_meter_stalled", f"{well} {x}..{y}"
        if dv > 0 and dh <= 0:
            return "hour_meter_stalled", f"{well} {x}..{y}"
    return None, None


VOLUME_PROBLEMS = ("volume_meter_stalled", "well_status_conflict")     # make the metered volume unknown


def inventory_report(store: FactStore, rules: dict) -> dict:
    """Fields with meter or pump-hour records, and those among them without a declared well
    inventory (every irrigation and balance question for those becomes an abstention)."""
    metered, missing = [], []
    for f in store.fields.values():
        fw = field_water(store, f, rules)
        if fw.of("meter") or fw.of("pump_hours"):
            metered.append(f.key)
            if inventory_for(store, f, rules) is None:
                missing.append(f.key)
    return {"metered_fields": len(metered), "without_inventory": missing}


def stress_class(dr: float, raw: float, taw: float, p: float, rules: dict) -> tuple[str, float]:
    ks = ks_of(dr, taw, p)
    if dr <= raw:
        return "no_stress", ks
    return ("moderate" if ks >= rules["water"]["ks_severe"] else "severe"), ks


def kc_refs(series: Series, a: dt.date, b: dt.date) -> list[dict]:
    """Exact records establishing Kc at the first modelled day and every later change."""
    dates = series.days()
    preceding = [d for d in dates if d <= a]
    used = ([preceding[-1]] if preceding else []) + [d for d in dates if a < d <= b]
    return [{**series.ref(d, d), "record_keys": [r.key for r in series.records[d]],
             "recorded_at": [r.recorded_ts.isoformat() for r in series.records[d]]} for d in used]

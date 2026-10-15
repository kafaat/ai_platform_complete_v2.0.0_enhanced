"""Build a labelled SYNTHETIC demo with three independent sites.

  الجوف   → train   (real Al-Sunaidar soil values + invented boundaries)
  مأرب    → val     (invented)
  الحديدة → test    (invented; covers every family incl. images and varied abstention)

Soil readings for "field_alsunaidar" are the 2022 and 2025 lab values from the
SAHOOL Al-Jawf seed (sahool_seed_aljawf_alsunaidar.sql), with the 2025 GPS
points. Everything else — boundaries, other sites, wells, SAVI series and
rasters — is invented to exercise every question family and audit check,
including planted faults (wrong stored area, swapped coordinates, a foreign
tenant row, out-of-range values, an unknown unit, a near-boundary point).
The fixture and every raster sidecar are flagged synthetic.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import random
from pathlib import Path

from .geo import LocalFrame, utm_forward

TENANT = "demo-tenant"


def circle(lon, lat, r_m, n=96):
    fr = LocalFrame(lon, lat)
    return [fr.inv(r_m * math.sin(2 * math.pi * i / n), r_m * math.cos(2 * math.pi * i / n)) for i in range(n)]


def rect(lon, lat, w_m, h_m, rot_deg=0.0):
    fr = LocalFrame(lon, lat)
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    pts = [(-w_m / 2, -h_m / 2), (w_m / 2, -h_m / 2), (w_m / 2, h_m / 2), (-w_m / 2, h_m / 2)]
    return [fr.inv(x * c - y * s, x * s + y * c) for x, y in pts]


def offsets(lon, lat, pts_m):
    fr = LocalFrame(lon, lat)
    return [fr.inv(x, y) for x, y in pts_m]


def poly_geojson(ring):
    """Exterior ring counter-clockwise, as RFC 7946 §3.1.6 asks."""
    pts = [[round(x, 7), round(y, 7)] for x, y in ring]
    if sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])) < 0:
        pts = pts[::-1]
    return {"type": "Polygon", "coordinates": [pts + [pts[0]]]}


def feature(geom, **props):
    return {"type": "Feature", "geometry": geom, "properties": props}


def point(lon, lat):
    return {"type": "Point", "coordinates": [round(lon, 8), round(lat, 8)]}


SOIL_2022 = [  # sensor, pH, EC dS/m, OM %  (SAHOOL seed, Al-Sunaidar 2022, no coordinates)
    ("SA-1", 7.00, 1.113, 0.16), ("SA-2", 8.57, 1.306, 0.34), ("SA-3", 8.55, 0.990, 0.22),
    ("SA-4", 8.45, 1.232, 0.11), ("SA-5", 8.58, 0.977, 0.05), ("SA-8", 8.44, 0.688, 0.38),
    ("SA-9", 8.80, 0.569, 0.42), ("SA-10", 7.11, 0.467, 0.38), ("SA-12", 7.07, 0.440, 0.26),
    ("SA-14", 7.07, 0.389, 0.09)]
SOIL_2025 = [  # sensor, pH, EC, N mg/kg, P, K, lat, lon  (SAHOOL seed 2025 GPS)
    ("2025-1", 8.10, 2.61, 200.0, 2.21, 345.0, 16.09071159, 44.94250488),
    ("2025-2", 8.23, 2.48, 380.0, 2.24, 281.0, 16.09703636, 44.94490051),
    ("2025-3", 7.89, 4.10, 50.0, 1.02, 256.0, 16.09071159, 44.94134903),
    ("2025-4", 7.94, 6.75, 540.0, 2.21, 312.0, 16.09866714, 44.94691086),
    ("2025-5", 7.99, 3.38, 340.0, 2.85, 329.0, 16.09601784, 44.94709396),
    ("2025-6", 8.09, 4.25, 380.0, 2.45, 296.0, 16.09601784, 44.94709396)]

# Al-Jawf (train)
PIVOT1, PIVOT2, FLOOD = (44.9420, 16.0905), (44.9465, 16.0975), (44.9530, 16.0905)
ORCHARD, WINDBREAK = (44.9395, 16.1000), (44.9535, 16.0960)
# Tihama / Al-Hudaydah (test)
TIHAMA1, TIHAMA2, TPIVOT = (43.2500, 14.3000), (43.2560, 14.3045), (43.2620, 14.2960)
# Marib (val)
MARIB1, MPIVOT = (45.3200, 15.4500), (45.3275, 15.4560)

PROVENANCE = {
    "soil:field_alsunaidar:2022": "قيم مخبرية حقيقية (EC، pH، مادة عضوية) من ملف seed سهول "
                                  "sahool_seed_aljawf_alsunaidar.sql — تقارير المختبر الوطني 2022؛ بلا إحداثيات",
    "soil:field_alsunaidar:2025": "قيم مخبرية حقيقية (EC، pH، N، P2O5، K2O) مع إحداثيات GPS من الملف نفسه؛ "
                                  "N محوّل من % إلى mg/kg (×10000) في ملف الـ seed",
    "everything_else": "اصطناعي: الحدود، موقعا مأرب والحديدة، الآبار، سلاسل SAVI، الطبقات النقطية، والأعطال المزروعة",
    "note": "ملفات المختبر الأصلية غير مرفقة هنا؛ تحقّق من القيم مقابلها قبل نسبتها إلى المختبر",
}


PROVENANCE["water_well_inventory"] = {
    f"{TENANT}::{field_id}": [{"from": "2025-01-01", "to": "2026-12-31", "wells": wells}]
    for field_id, wells in {
        "demo_pivot_1": ["P1A", "P1B"], "demo_pivot_2": ["P2A", "P2B"],
        "demo_marib_pivot": ["MP1", "MP2"], "demo_marib_1": ["M1"],
        "demo_tihama_pivot": ["TP1", "TP2"], "demo_tihama_1": ["T12"],
        "demo_tihama_2": ["T12"], "demo_tihama_farm": ["TF"], "demo_orchard": ["OR1"],
        "demo_tihama_strip": ["TS1"],
    }.items()
}


def _savi_series(fid, start, n, step, peak_day, peak, rng, tenant=TENANT, width=45):
    out = []
    for k in range(n):
        d = start + dt.timedelta(days=step * k)
        t = (d - start).days
        val = 0.06 + (peak - 0.06) * math.exp(-((t - peak_day) / width) ** 2) + rng.uniform(-0.012, 0.012)
        out.append(feature(None, kind="indicator", field_id=fid, indicator_id="savi", category="vegetation",
                           value=round(val, 3), unit="index", source="sentinel-2", recorded_at=f"{d}T10:30:00+03:00",
                           tenant=tenant))
    return out


RAIN_SRC = {"station": "farm-gauge", "chirps_v3_rnl": "CHIRPS-v3.0 daily rnl", "era5land": "ERA5-Land"}


def _water_block(fid, start: dt.date, n: int, *, et0, kc_steps, rain=None, wells=None, theta0=None,
                 theta_unit="%", plan=None, drop=(), resets=None, tenant=TENANT, soil_day=0, extra=(),
                 status=None, stall=None):
    """Daily water records for one field (synthetic).

    et0       — callable(day index) -> mm
    kc_steps  — [(date string, kc)]
    rain      — {source: {day index: mm}}; every other day of the window records 0
    wells     — {well: (flow m3/h, callable(day index) -> pump hours, meter start, hour-meter start)};
                one reading per day at 21:00 (after the day's pumping)
    plan      — {week index: planned gross mm for the 7 days from start + 1 + 7*week}
    extra     — [(indicator_id, day index, "HH:MM", value)] additional same-day records
    drop      — {(indicator_id, day index)} records left out (missing readings)
    resets    — {(well, day index): new meter value} (meter replaced: reading restarts low)
    status    — {well: [(day index, 1 | 0)]} well_status records (0 = out of service), recorded at 07:00
    stall     — {well: (first day, last day)} the volume register does not count on those days while
                the pump (and its hour meter) keeps running: a stuck meter
    """
    out = []

    def rec(iid, d, value, unit, source, hhmm="08:00", cat="water"):
        k = (d - start).days
        if (iid, k) in drop:
            return
        out.append(feature(None, kind="indicator", field_id=fid, indicator_id=iid, category=cat, value=value,
                           unit=unit, source=source, recorded_at=f"{d}T{hhmm}:00+03:00", tenant=tenant))

    days = [start + dt.timedelta(days=k) for k in range(n)]
    if theta0 is not None:
        rec("soil_moisture_vol", days[soil_day], theta0, theta_unit, "probe-30cm", "07:30")
    for k, d in enumerate(days):
        rec("et0_mm", d, round(et0(k), 2), "mm/day", "ERA5-Land PM", "23:00", "weather")
        for src, ev in (rain or {}).items():
            rec(f"rain_mm_{src}", d, ev.get(k, 0.0), "mm", RAIN_SRC[src], "23:30", "weather")
    for ds, kc in kc_steps:
        rec("kc", dt.date.fromisoformat(ds), kc, None, "crop-calendar", "00:00", "crop")
    for well, (flow, hours, m0, h0) in (wells or {}).items():
        m, h = float(m0), float(h0)
        for k, d in enumerate(days):
            if k > 0:
                hh = hours(k)
                stuck = stall and well in stall and stall[well][0] <= k <= stall[well][1]
                m, h = m + (0.0 if stuck else flow * hh), h + hh
            if resets and (well, k) in resets:
                m = resets[(well, k)]
            rec(f"meter_total_{well}", d, round(m, 1), "m3", "flowmeter", "21:00")
            rec(f"pump_hours_{well}", d, round(h, 2), "h", "hour-meter", "21:00")
    for well, recs in (status or {}).items():
        for k, value in recs:
            rec(f"well_status_{well}", days[k], value, None, "farm-log", "07:00")
    for wk, mm in (plan or {}).items():
        rec("irrigation_plan_week", start + dt.timedelta(days=1 + 7 * wk), mm, "mm", "irrigation-plan", "00:00")
    units = {"rain_mm_": ("mm", None), "meter_total_": ("m3", "flowmeter"), "pump_hours_": ("h", "hour-meter")}
    for iid, k, hhmm, value in extra:
        unit, src = next(v for pre, v in units.items() if iid.startswith(pre))
        rec(iid, start + dt.timedelta(days=k), value, unit, src or RAIN_SRC[iid[len("rain_mm_"):]], hhmm)
    return out


def weekly(*hours):
    """Pump hours per day, one value per 7-day block from day 1 (day index k >= 1)."""
    return lambda k: hours[min((k - 1) // 7, len(hours) - 1)]


def _wave(base, amp, period=9.0, phase=0.0):
    return lambda k: base + amp * math.sin(2 * math.pi * k / period + phase)


def build_water(feats: list):
    """Water investigation records (0.4.0), one season window per site, with planted traps:
    a pump failure (stress), missing meter readings (daily split unknown, total known), a meter
    replacement, a well shared by two fields, a field with no meter, a tensiometer reading in kPa,
    a gauge gap (balance falls back to the next rain source), a missing plan week, a field
    without a polygon, and rain events confirmed / not confirmed / only by a same-lineage product."""
    # ── Al-Jawf (train): 2026-01-05 .. 2026-02-02 ──
    j0, n = dt.date(2026, 1, 5), 29
    grid = {"era5land": {12: 0.3, 13: 6.1, 14: 0.4, 20: 0.2, 21: 7.4, 22: 0.6},
            "chirps_v3_rnl": {13: 7.0, 21: 6.6}}
    et0 = _wave(4.2, 0.35)
    kc = [("2025-12-20", 0.7), ("2026-01-15", 1.15)]
    feats += _water_block(
        "demo_pivot_1", j0, n, et0=et0, kc_steps=kc, theta0=18.0,
        rain={**grid, "station": {13: 8.4}}, extra=[("rain_mm_station", 13, "23:45", 8.2)],   # second entry: mean
        wells={"P1A": (150.0, lambda k: 9.0 if k <= 8 else 6.5 if k <= 21 else 0.0, 182340.0, 5120.0),  # diesel cut
               "P1B": (130.0, lambda k: 9.0 if k <= 8 else 0.0, 97410.0, 3311.0)},                      # pump failure
        status={"P1B": [(0, 1), (9, 0)]},                       # failure logged; the later diesel cut on P1A is not
        plan={0: 30.0, 1: 30.0, 2: 32.0, 3: 32.0})
    feats += _water_block(
        "demo_pivot_2", j0, n, et0=et0, kc_steps=kc, theta0=14.3,
        rain={**grid, "station": {13: 7.9}},
        wells={"P2A": (140.0, weekly(7.0, 6.8, 6.5, 7.2), 61200.0, 2050.0),
               "P2B": (140.0, weekly(7.0, 6.8, 6.5, 7.2), 58800.0, 1990.0)},
        drop={("meter_total_P2A", 16), ("meter_total_P2A", 17), ("meter_total_P2A", 18)},   # gap: daily split unknown
        plan={0: 20.0, 1: 20.0, 2: 20.0, 3: 20.0})
    feats += _water_block("demo_orchard", j0, n, et0=et0, kc_steps=[],
                          wells={"OR1": (60.0, weekly(6.0, 5.5, 6.5, 5.0), 12650.0, 830.0)},
                          stall={"OR1": (10, 13)})                     # volume register stuck 01-15..01-18, pump running
    feats += _water_block(
        "demo_flood", j0, n, et0=et0, kc_steps=[("2026-01-01", 1.0)], theta0=24.0,
        rain={**grid, "station": {13: 9.2}}, drop={("rain_mm_station", 12), ("rain_mm_station", 13)})  # no meter
    # ── Marib (val): 2026-01-10 .. 2026-02-07 ──
    m0 = dt.date(2026, 1, 10)
    mgrid = {"era5land": {7: 0.2, 8: 0.4, 19: 1.1, 20: 8.0, 21: 0.9}, "chirps_v3_rnl": {8: 1.0, 20: 9.1}}
    met0 = _wave(3.9, 0.3, 11.0)
    mkc = [("2025-12-25", 0.75), ("2026-01-20", 1.15)]
    feats += _water_block(
        "demo_marib_pivot", m0, n, et0=met0, kc_steps=mkc, theta0=13.0,
        rain={**mgrid, "station": {8: 6.0, 20: 7.5}},
        wells={"MP1": (160.0, lambda k: 9.5, 240510.0, 7400.0), "MP2": (110.0, weekly(4.0, 4.5, 3.5, 4.2), 88020.0, 2604.0)},
        resets={("MP1", 15): 12.0},                                                            # meter replaced
        plan={0: 36.0, 1: 36.0, 2: 36.0, 3: 36.0})
    feats += _water_block(
        "demo_marib_1", m0, n, et0=met0, kc_steps=mkc, theta0=28.0, theta_unit="kPa",          # tensiometer, not vol %
        rain=mgrid, wells={"M1": (90.0, weekly(6.0, 5.5, 6.5, 5.5), 30500.0, 1210.0)},
        plan={0: 26.0, 1: 26.0, 2: 26.0, 3: 26.0})
    # ── Al-Hudaydah / Tihama (test): 2026-07-01 .. 2026-07-29 ──
    t0 = dt.date(2026, 7, 1)
    tgrid = {"era5land": {8: 0.8, 9: 9.0, 10: 1.2, 19: 0.5, 20: 6.0, 21: 0.7},
             "chirps_v3_rnl": {9: 11.0, 20: 7.5}}
    tet0 = _wave(6.6, 0.45, 8.0)
    tkc = [("2026-06-20", 0.7), ("2026-07-12", 1.0)]
    feats += _water_block(
        "demo_tihama_pivot", t0, n, et0=tet0, kc_steps=tkc, theta0=27.0,
        rain={**tgrid, "station": {9: 14.0}},
        drop={("rain_mm_station", 19), ("rain_mm_station", 20), ("rain_mm_station", 21)},  # gauge gap at the 2nd event
        wells={"TP1": (120.0, lambda k: 7.0 if k <= 7 else 0.0, 51000.0, 3010.0),   # no diesel from 07-09
               "TP2": (100.0, lambda k: 8.0 if k <= 7 else 0.0, 44100.0, 2400.0)},
        extra=[("meter_total_TP1", 4, "06:00", 53520.0)],                          # morning reading: the later one counts
        status={"TP1": [(0, 1), (8, 0)], "TP2": [(0, 1), (8, 0)]},                  # no diesel, logged: flow is a known zero
        plan={0: 55.0, 1: 55.0, 2: 55.0, 3: 55.0})
    shared = {"T12": (110.0, lambda k: 10.0, 20400.0, 980.0)}
    gauge12 = {**tgrid, "station": {9: 12.5}}                                       # one gauge for both fields
    feats += _water_block("demo_tihama_1", t0, n, et0=tet0, kc_steps=tkc, theta0=27.0, rain=gauge12, wells=shared)
    feats += _water_block("demo_tihama_2", t0, n, et0=tet0, kc_steps=[("2026-06-25", 0.6)], rain=gauge12, wells=shared,
                          plan={0: 40.0, 1: 40.0, 3: 40.0})                              # week 2 missing
    feats += _water_block("demo_tihama_farm", t0, n, et0=tet0, kc_steps=tkc,
                          wells={"TF": (70.0, lambda k: 8.0, 9100.0, 400.0)})                 # no polygon
    feats += _water_block("demo_tihama_strip", t0, n, et0=tet0, kc_steps=[],
                          wells={"TS1": (40.0, weekly(8.0, 7.0, 7.5, 6.0), 3200.0, 150.0)},
                          stall={"TS1": (15, 18)})                     # volume register stuck 07-16..07-19, pump running


def build_fixture() -> dict:
    feats = []
    jawf = dict(tenant=TENANT, governorate="الجوف")
    tih = dict(tenant=TENANT, governorate="الحديدة")
    mar = dict(tenant=TENANT, governorate="مأرب")

    # ── Al-Jawf (train) ──
    feats.append(feature(None, kind="field", id="field_alsunaidar", name="مزرعة السنيدار (الحزم)", crop="قمح",
                         soil_type="sandy_loam", latitude=16.0960, longitude=44.9460, area_ha=None, **jawf))
    feats.append(feature(poly_geojson(circle(*PIVOT1, 401)), kind="field", id="demo_pivot_1", name="المحور 1 (عرض)",
                         crop="قمح", soil_type="sandy_loam", **jawf))
    feats.append(feature(poly_geojson(circle(*PIVOT2, 401)), kind="field", id="demo_pivot_2", name="المحور 2 (عرض)",
                         crop="قمح", area_ha=50.5, soil_type="loamy_sand", **jawf))
    feats.append(feature(poly_geojson(rect(*FLOOD, 400, 250, 8)), kind="field", id="demo_flood", name="حوض الغمر (عرض)",
                         crop="ذرة رفيعة", soil_type="loam", **jawf))
    feats.append(feature(poly_geojson(offsets(*ORCHARD, [(-140, -90), (120, -110), (170, 40), (30, 150), (-160, 80)])),
                         kind="field", id="demo_orchard", name="البستان (عرض)", crop="نخيل", **jawf))
    feats.append(feature(poly_geojson(rect(*WINDBREAK, 600, 40, 0)), kind="field", id="demo_windbreak",
                         name="مصدّ الرياح (عرض)", crop=None, **jawf))
    for sid, ph, ec, om in SOIL_2022:
        feats.append(feature(None, kind="soil", field_id="field_alsunaidar", sample_id=sid, ph=ph, ec=ec, om=om,
                             depth_cm=60, source="lab", recorded_at="2022-09-07", tenant=TENANT))
    for sid, ph, ec, n, p, k, lat, lon in SOIL_2025:
        feats.append(feature(point(lon, lat), kind="soil", field_id="field_alsunaidar", sample_id=sid, ph=ph, ec=ec,
                             n=n, p=p, k=k, depth_cm=60, source="lab", recorded_at="2025-01-01", tenant=TENANT))
    for i, ((lon, lat), ec, ph) in enumerate(zip(offsets(*FLOOD, [(-90, -40), (100, 30), (20, 80)]),
                                                 (5.9, 6.4, 6.1), (8.3, 8.4, 8.2)), 1):
        feats.append(feature(point(lon, lat), kind="soil", field_id="demo_flood", sample_id=f"DEMO-F{i}", ph=ph, ec=ec,
                             depth_cm=30, source="lab", recorded_at="2025-03-10", tenant=TENANT))
    edge = offsets(*PIVOT1, [(0, 401 * math.cos(math.pi / 96) - 0.4)])[0]   # ~0.4 m inside pivot 1's north edge
    feats.append(feature(point(*edge), kind="soil", field_id="demo_pivot_1", sample_id="DEMO-EDGE", ph=8.0, ec=3.0,
                         depth_cm=60, source="lab", recorded_at="2025-01-01", tenant=TENANT))
    wells = [("water_ec_W1", 0.92, "dS/m"), ("water_ec_W2", 1450.0, "µS/cm"), ("water_ec_W3", 2.6, "dS/m"),
             ("water_ec_W4", 0.6, "dS/m"), ("water_ec_W5", 700.0, "ppm"), ("water_ec_W6", 12.0, "meq/L")]
    wpts = offsets(*PIVOT2, [(-60, 0), (60, 10), (0, -60)]) + offsets(*PIVOT1, [(0, 50), (40, -30), (-50, 20)])
    for (iid, val, unit), (lon, lat) in zip(wells, wpts):
        feats.append(feature(point(lon, lat), kind="indicator", field_id="field_alsunaidar", indicator_id=iid,
                             category="water", value=val, unit=unit, source="lab", recorded_at="2023-05-20", tenant=TENANT))
    rng = random.Random(42)
    for fid, peak in (("demo_pivot_1", 0.62), ("demo_pivot_2", 0.55), ("demo_flood", 0.48)):
        feats += _savi_series(fid, dt.date(2025, 11, 5), 15, 12, 100, peak, rng)
    feats += _savi_series("demo_orchard", dt.date(2025, 11, 5), 12, 12, 70, 0.15, rng)    # never reaches 0.2

    # ── Marib (val) ──
    feats.append(feature(poly_geojson(rect(*MARIB1, 450, 300, 20)), kind="field", id="demo_marib_1",
                         name="حقل مأرب 1 (عرض)", crop="شعير", soil_type="loam", **mar))
    feats.append(feature(poly_geojson(circle(*MPIVOT, 350)), kind="field", id="demo_marib_pivot",
                         name="محور مأرب (عرض)", crop="قمح", soil_type="sandy_loam", **mar))
    for i, (lon, lat) in enumerate(offsets(*MARIB1, [(-100, -50), (80, 40), (0, 100)]), 1):
        feats.append(feature(point(lon, lat), kind="soil", field_id="demo_marib_1", sample_id=f"M1-{i}",
                             ph=(7.9, 8.1, 8.0)[i - 1], ec=(1.8, 2.3, 2.0)[i - 1], depth_cm=30, source="lab",
                             recorded_at="2025-11-20", tenant=TENANT))
    for i, (lon, lat) in enumerate(offsets(*MARIB1, [(-100, -50), (80, 40), (0, 100)]), 1):
        feats.append(feature(point(lon, lat), kind="soil", field_id="demo_marib_1", sample_id=f"M1-{i}",
                             ph=7.9, ec=(1.1, 1.3, 1.2)[i - 1], depth_cm=30, source="lab",
                             recorded_at="2023-11-18", tenant=TENANT))
    for i, (lon, lat) in enumerate(offsets(*MPIVOT, [(-120, 60), (90, -80), (30, 150)]), 1):
        feats.append(feature(point(lon, lat), kind="soil", field_id="demo_marib_pivot", sample_id=f"MP-{i}",
                             ph=8.2, ec=(4.6, 5.2, 4.9)[i - 1], depth_cm=30, source="lab",
                             recorded_at="2025-11-20", tenant=TENANT))
    feats += _savi_series("demo_marib_pivot", dt.date(2025, 11, 10), 14, 12, 95, 0.58, rng)
    feats += _savi_series("demo_marib_1", dt.date(2026, 2, 1), 10, 10, 5, 0.50, rng)     # starts above: onset unknown
    feats.append(feature(point(*offsets(*MPIVOT, [(0, 0)])[0]), kind="indicator", field_id="demo_marib_pivot",
                         indicator_id="water_ec_MW1", category="water", value=0.55, unit="dS/m", source="lab",
                         recorded_at="2025-10-01", tenant=TENANT))

    # ── Al-Hudaydah / Tihama (test) ──
    feats.append(feature(None, kind="field", id="demo_tihama_farm", name="مزرعة تهامة (عرض)", crop="ذرة رفيعة",
                         latitude=14.300, longitude=43.255, area_ha=18.0, **tih))
    feats.append(feature(poly_geojson(rect(*TIHAMA1, 500, 420, -12)), kind="field", id="demo_tihama_1",
                         name="حقل تهامة 1 (عرض)", crop="ذرة رفيعة", soil_type="silt_loam", **tih))
    feats.append(feature(poly_geojson(offsets(*TIHAMA2, [(-150, -160), (210, -120), (190, 140), (-40, 210), (-190, 60)])),
                         kind="field", id="demo_tihama_2", name="حقل تهامة 2 (عرض)", crop="سمسم",
                         area_ha=1200.0, soil_type="silt_loam", **tih))  # deliberately ~100x too large -> area_mismatch
    feats.append(feature(poly_geojson(circle(*TPIVOT, 300)), kind="field", id="demo_tihama_pivot",
                         name="محور تهامة (عرض)", crop="ذرة رفيعة", soil_type="silt_loam", **tih))
    feats.append(feature(poly_geojson(rect(TIHAMA1[0] - 0.008, TIHAMA1[1] + 0.004, 700, 45, 0)), kind="field",
                         id="demo_tihama_strip", name="شريط تهامة (عرض)", crop=None, **tih))
    t1 = offsets(*TIHAMA1, [(-120, -80), (90, 60), (10, 150), (-60, 110)])
    for i, (lon, lat) in enumerate(t1, 1):
        for year, ec in ((2024, (1.4, 1.6, 1.5, 1.7)[i - 1]), (2026, (1.5, 1.7, 1.55, 1.75)[i - 1])):
            feats.append(feature(point(lon, lat), kind="soil", field_id="demo_tihama_1", sample_id=f"T1-{i}",
                                 ph=round(7.6 + 0.1 * i, 2), ec=ec, depth_cm=30, source="lab",
                                 recorded_at=f"{year}-04-15", tenant=TENANT))
    feats.append(feature(None, kind="soil", field_id="demo_tihama_1", sample_id="T1-BAD", ph=99, ec=-1, n="NaN",
                         depth_cm=30, source="lab", recorded_at="2026-04-15", tenant=TENANT))   # QC failures
    feats.append(feature(point(*t1[0]), kind="soil", field_id="demo_tihama_1", sample_id="FOREIGN-1", ec=9.9,
                         recorded_at="2026-04-15", tenant="other-tenant"))                    # must be rejected
    for i, (lon, lat) in enumerate(offsets(*TPIVOT, [(-100, 50), (80, -60), (20, 140)]), 1):
        feats.append(feature(point(lon, lat), kind="soil", field_id="demo_tihama_pivot", sample_id=f"TP-{i}",
                             ph=7.9, ec=(3.2, 3.6, 3.4)[i - 1], k=(210.0, None, 190.0)[i - 1], depth_cm=30,
                             source="lab", recorded_at="2026-04-16", tenant=TENANT))
    lon, lat = offsets(*TIHAMA2, [(0, 0)])[0]
    feats.append(feature(point(lat, lon), kind="soil", field_id="demo_tihama_2", sample_id="T2-1", ph=7.4, ec=2.2,
                         depth_cm=30, source="lab", recorded_at="2026-04-15", tenant=TENANT))  # lat/lon swapped on purpose
    feats.append(feature(None, kind="soil", field_id="demo_tihama_farm", sample_id="TF-1", ph=7.7, ec=1.9,
                         depth_cm=30, source="lab", recorded_at="2026-04-15", tenant=TENANT))
    feats.append(feature(None, kind="soil", field_id="demo_tihama_farm", sample_id="TF-2", ph=7.8, ec=2.1,
                         depth_cm=30, source="lab", recorded_at="2026-04-15", tenant=TENANT))
    for iid, val, unit, at in (("water_ec_TW1", 1.1, "dS/m", TIHAMA1), ("water_ec_TW2", 9.5, "meq/L", TPIVOT),
                                ("water_ec_TW3", 900.0, "ppm", TIHAMA2)):
        feats.append(feature(point(*offsets(*at, [(30, -40)])[0]), kind="indicator", field_id="demo_tihama_farm",
                             indicator_id=iid, category="water", value=val, unit=unit, source="lab",
                             recorded_at="2026-05-02", tenant=TENANT))
    for fid, peak in (("demo_tihama_pivot", 0.57), ("demo_tihama_1", 0.44)):
        feats += _savi_series(fid, dt.date(2026, 6, 1), 13, 10, 75, peak, rng)
    feats += _savi_series("demo_tihama_2", dt.date(2026, 6, 5), 10, 10, 5, 0.45, rng)    # starts above: onset unknown
    build_water(feats)
    return {"type": "FeatureCollection",
            "sahool_qa": {"synthetic": True, "description": __doc__.strip().splitlines()[0], "provenance": copy.deepcopy(PROVENANCE)},
            "features": feats}


def _raster(fixture, field_ids, base, effects, date, scene, out_dir, shift=0.0, pad=300.0, role="all"):
    """One synthetic SAVI scene in UTM 38N (EPSG:32638), 10 m pixels, covering the given fields.

    effects: list of (field_id, kind, arg) with kind
      quad   — 90° quadrant ("NE", "SE", "SW", "NW") weak
      sector — 45° sector centred on a compass key ("N", "NE", "E", …) weak
      ring   — radial band (from, to) as fractions of the equivalent radius weak
      cloud  — sector key or "N_half": pixels set to nodata (masked cloud)
    """
    import numpy as np

    from .geo import Geometry
    geoms = {ft["properties"]["id"]: Geometry.from_geojson(ft["geometry"]) for ft in fixture["features"]
             if ft["properties"].get("kind") == "field" and ft["geometry"] and ft["properties"]["id"] in field_ids}
    xs, ys = [], []
    for g in geoms.values():
        for lon, lat in g.all_points():
            x, y = utm_forward(lon, lat, 38)
            xs.append(x)
            ys.append(y)
    px = 10.0
    x0 = math.floor((min(xs) - pad) / px) * px
    y0 = math.ceil((max(ys) + pad) / px) * px
    w = int((max(xs) + pad - x0) / px) + 1
    h = int((y0 - (min(ys) - pad)) / px) + 1
    X, Y = np.meshgrid(x0 + (np.arange(w) + 0.5) * px, y0 - (np.arange(h) + 0.5) * px)

    def mask(g):
        ring = [utm_forward(lon, lat, 38) for lon, lat in g.polygons[0][0]]
        m = np.zeros(X.shape, dtype=bool)
        with np.errstate(divide="ignore", invalid="ignore"):
            for i in range(len(ring)):
                xi, yi = ring[i]
                xj, yj = ring[i - 1]
                m ^= ((yi > Y) != (yj > Y)) & (X < (xj - xi) * (Y - yi) / (yj - yi) + xi)
        return m

    def polar(g):
        cx, cy = utm_forward(*g.centroid, 38)
        dx, dy = X - cx, Y - cy
        return np.hypot(dx, dy) / math.sqrt(g.area_m2 / math.pi), (np.degrees(np.arctan2(dx, dy)) + 360) % 360

    keys = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    rs = np.random.default_rng(int(date.replace("-", "")) + sum(map(ord, scene)))   # deterministic per scene
    arr = rs.normal(0.08, 0.02, X.shape)
    for fid, b in base.items():
        m = mask(geoms[fid])
        arr[m] = rs.normal(b + shift, 0.05, int(m.sum()))
    for fid, kind, arg in effects:
        g = geoms[fid]
        rr, az = polar(g)
        if kind == "quad":
            lo = {"NE": 0, "SE": 90, "SW": 180, "NW": 270}[arg]
            sel = (az >= lo) & (az < lo + 90)
        elif kind in ("sector", "cloud") and arg in keys:
            c = 45 * keys.index(arg)
            sel = ((az - c + 22.5) % 360) < 45
        elif kind == "cloud" and arg == "N_half":
            sel = (az >= 270) | (az < 90)
        elif kind == "ring":
            sel = (rr >= arg[0]) & (rr < arg[1])
        else:
            raise ValueError(kind)
        m = mask(g) & sel
        if kind == "cloud":
            arr[m] = -9999.0
        else:
            arr[m] = rs.normal(0.13, 0.04, int(m.sum()))
    if role == "all":
        arr[: max(1, h // 12), : max(1, w // 6)] = -9999.0    # a nodata corner (cloud mask) away from the fields
    npy = out_dir / f"savi_{scene}.npy"
    np.save(npy, arr.astype("float32"))
    (out_dir / f"savi_{scene}.json").write_text(json.dumps(
        {"array": npy.name, "index": "SAVI", "date": date, "crs": "EPSG:32638", "transform": [x0, px, 0, y0, 0, -px],
         "nodata": -9999.0, "scene_id": scene, "synthetic": True, "role": role,
         "product_version": "demo-L2A-N0511"}, indent=2), encoding="utf-8")


TIMELINES = {
    # field: (dates, base, {scene index: [(kind, arg), ...]}) — what the onset question must find
    "demo_pivot_1": (["2025-03-01", "2025-03-11", "2025-03-21", "2025-03-31", "2025-04-10", "2025-04-20"], 0.50,
                     {0: [("sector", "E")], 2: [("cloud", "E")], 3: [("sector", "E")], 4: [("sector", "E")],
                      5: [("sector", "E")]}),                                    # onset between 03-11 and 03-31
    "demo_pivot_2": (["2025-03-01", "2025-03-11", "2025-03-21", "2025-03-31", "2025-04-10", "2025-04-20"], 0.47,
                     {2: [("sector", "W")]}),                                    # one-off dip only: no reliable divergence
    "demo_marib_pivot": (["2025-04-05", "2025-04-15", "2025-04-25", "2025-05-05", "2025-05-15"], 0.50,
                         {0: [("cloud", "N_half"), ("sector", "S")], 1: [("sector", "S")], 2: [("sector", "S")],
                          3: [("sector", "S")], 4: [("sector", "S")]}),          # present from first valid scene: unknown
    "demo_tihama_pivot": (["2025-08-02", "2025-08-12", "2025-08-22", "2025-09-01", "2025-09-11", "2025-09-21"], 0.49,
                          {1: [("sector", "SE")], 3: [("cloud", "SE")], 4: [("sector", "SE")],
                           5: [("sector", "SE")]}),                              # onset between 08-22 and 09-11
}


def build_rasters(fixture: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    jawf = {"demo_pivot_1": 0.52, "demo_pivot_2": 0.47, "demo_flood": 0.33, "demo_orchard": 0.28}
    _raster(fixture, set(jawf), jawf, [("demo_pivot_1", "quad", "NE")], "2026-02-15", "S2B_20260215_JAWF_DEMO", out_dir)
    _raster(fixture, set(jawf), jawf, [("demo_pivot_2", "ring", (0.6, 0.8)), ("demo_pivot_1", "cloud", "N_half")],
            "2026-03-21", "S2A_20260321_JAWF_DEMO", out_dir, shift=-0.04)
    marib = {"demo_marib_1": 0.30, "demo_marib_pivot": 0.50}
    _raster(fixture, set(marib), marib, [("demo_marib_pivot", "quad", "NW")], "2026-01-20", "S2B_20260120_MARIB_DEMO", out_dir)
    _raster(fixture, set(marib), {"demo_marib_1": 0.30, "demo_marib_pivot": 0.13}, [], "2026-02-25",
            "S2A_20260225_MARIB_DEMO", out_dir)                                   # field-wide weakness
    tih = {"demo_tihama_1": 0.36, "demo_tihama_pivot": 0.49, "demo_tihama_2": 0.24}
    _raster(fixture, set(tih), tih, [("demo_tihama_pivot", "quad", "SW")], "2026-08-20", "S2A_20260820_TIHAMA_DEMO", out_dir)
    _raster(fixture, set(tih), tih, [("demo_tihama_pivot", "ring", (0.4, 0.6))], "2026-09-05", "S2B_20260905_TIHAMA_DEMO",
            out_dir)
    _raster(fixture, set(tih), tih, [("demo_tihama_pivot", "cloud", "N_half")], "2026-09-15", "S2A_20260915_TIHAMA_DEMO",
            out_dir)                                                              # half the pivot under cloud
    for fid, (dates, base, eff) in TIMELINES.items():
        for i, d in enumerate(dates):
            _raster(fixture, {fid}, {fid: base}, [(fid, k, a) for k, a in eff.get(i, [])], d,
                    f"TL_{fid}_{d.replace('-', '')}", out_dir, pad=150.0, role="timeline-only")


def write_demo(out_dir: str) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fx = build_fixture()
    fx_path = out / "demo_fixture.geojson"
    fx_path.write_text(json.dumps(fx, ensure_ascii=False, indent=1), encoding="utf-8")
    build_rasters(fx, out / "rasters")
    return fx_path, out / "rasters"

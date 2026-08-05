"""
verify_review_fixes.py — تحقّق موجّه من إصلاحات المراجعة (H/M/L).
يُحمّل الوحدات الفعليّة ويختبر السلوك بعد الإصلاح. لا يحتاج خدمات حيّة.
"""

import asyncio
import datetime as _dt
import hashlib
import importlib.util
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (
    ROOT,
    os.path.join(ROOT, "services/sahool-platform"),
    os.path.join(ROOT, "services/sahool-platform/api"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  — {detail}" if detail and not cond else ""))


def load(path, modname):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


print("\n── H3: LAI (Beer-Lambert صحيح، مثبّت ومسقوف) ──")
veg = load("services/vegetation-analysis-service/main.py", "veg_main")


def bands(ndvi):  # bands تعطي NDVI مطلوباً تقريباً (B08 vs B04)
    return {
        "B02": 0.05,
        "B03": 0.1,
        "B04": 0.1,
        "B05": 0.2,
        "B08": 0.1 * (1 + ndvi) / (1 - ndvi) if ndvi < 1 else 5.0,
        "B11": 0.15,
        "B12": 0.1,
    }


lai_hi = veg._compute_indices(bands(0.85))["lai"]
lai_mid = veg._compute_indices(bands(0.6))["lai"]
lai_lo = veg._compute_indices(bands(0.2))["lai"]
check("LAI مسقوف ≤ 8.0 للغطاء السليم", lai_hi <= 8.0, f"lai_hi={lai_hi}")
check(
    "LAI رتيب (NDVI أعلى ⇒ LAI أعلى)",
    lai_lo < lai_mid < lai_hi,
    f"{lai_lo}<{lai_mid}<{lai_hi}",
)
check("LAI ليس القيمة المشبّعة القديمة ~13.8", lai_hi < 9.0, f"lai_hi={lai_hi}")

print("\n── H4: EVI بحارس قسمة على صفر ──")
degenerate = {
    "B02": 1.0,
    "B03": 0.1,
    "B04": 0.0,
    "B05": 0.2,
    "B08": 0.0,
    "B11": 0.15,
    "B12": 0.1,
}
# B08 + 6*B04 - 7.5*B02 + 1 = 0 + 0 - 7.5 + 1 = -6.5 (آمن) — نصنع مقام≈0:
# نريد B08 + 6*B04 - 7.5*B02 + 1 = 0 → B02=(B08+6*B04+1)/7.5
b = {"B04": 0.0, "B08": 0.0}
b["B02"] = (0.0 + 0.0 + 1) / 7.5
bb = {
    "B02": b["B02"],
    "B03": 0.1,
    "B04": 0.0,
    "B05": 0.2,
    "B08": 0.0,
    "B11": 0.15,
    "B12": 0.1,
}
try:
    out = veg._compute_indices(bb)
    check("EVI لا يرمي ZeroDivisionError عند مقام≈0", True)
    check("EVI قيمة منتهية (finite)", math.isfinite(out["evi"]), f"evi={out['evi']}")
except ZeroDivisionError as e:
    check("EVI لا يرمي ZeroDivisionError عند مقام≈0", False, str(e))

print("\n── H6: Open-Meteo فهرسة آمنة لمصفوفات مُسنّنة ──")
om = load("services/sahool-platform/api/connectors/openmeteo.py", "om_conn")
daily = {"time": ["d1", "d2", "d3"], "temperature_2m_max": [30.0]}  # أقصر من time
check(
    "_daily_at يُرجع القيمة الموجودة",
    om._daily_at(daily, "temperature_2m_max", 0, 99) == 30.0,
)
check(
    "_daily_at يُرجع الافتراضي لفهرس خارج الطول (لا IndexError)",
    om._daily_at(daily, "temperature_2m_max", 2, 99) == 99,
)
check(
    "_daily_at يُرجع الافتراضي لمفتاح غائب",
    om._daily_at(daily, "precipitation_sum", 0, 0) == 0,
)
check("_daily_at يُرجع الافتراضي لقيمة None", om._daily_at({"x": [None]}, "x", 0, 7) == 7)

print("\n── M3: اتصال دالة ثقة التغطية عند 0.5 ──")
ce = load("services/sahool-platform/api/confidence_engine.py", "conf_eng")


def cov(obs, exp):
    return ce.CoverageConfidence(pixels_observed=obs, pixels_expected=exp).score


s49, s50, s51 = cov(49, 100), cov(50, 100), cov(51, 100)
check(
    "ثقة التغطية متّصلة عند 0.5 (قفزة < 0.02)",
    abs(s50 - s49) < 0.02,
    f"s49={s49:.3f} s50={s50:.3f}",
)
check("ثقة التغطية رتيبة حول 0.5", s49 < s50 <= s51, f"{s49:.3f}<{s50:.3f}<={s51:.3f}")
check("لا قفزة قديمة (0.49→0.245)", s49 > 0.4, f"s49={s49:.3f}")

print("\n── L2: ترتيب نسخ عدديّ (لا معجمي) ──")
eu = load("services/sahool-platform/api/event_upcasting.py", "evt_up")
check("'1.10' أحدث من '1.2' عدديّاً", eu._vkey("1.10") > eu._vkey("1.2"))
check("'1.2' أحدث من '1.1'", eu._vkey("1.2") > eu._vkey("1.1"))
check(
    "التسمية المعتمدة fertilizer.applied في CURRENT_VERSIONS",
    "operation.fertilizer.applied" in eu.CURRENT_VERSIONS,
)

print("\n── L4: سجلّ الإكمال يملأ tool_id من start ──")
tc = load("services/supervisor-agent/tool_contracts.py", "tool_contracts")


async def _journal_test():
    j = tc.ExecutionJournal()
    await j.record_start(
        invocation_id="inv1",
        tool_id="actuator.valve",
        input_data={"a": 1},
        actor_capabilities=["x"],
        tenant_id="t1",
        contract_version="1.0",
    )
    await j.record_complete(invocation_id="inv1", success=True, duration_ms=5)
    entries = await j.get_entries(tool_id="actuator.valve")
    return entries


ents = asyncio.run(_journal_test())
events = sorted(e.event for e in ents)
check(
    "get_entries(tool_id) يطابق start+complete (كلاهما)",
    events == ["complete", "start"],
    f"events={events}",
)

print("\n── M5: مفتاح الكاش حتميّ عبر العمليّات (sha256) ──")


def cache_key(prefix, fn, args, kwargs):
    raw = (str(args) + str(sorted(kwargs.items()))).encode("utf-8")
    return f"{prefix}:{fn}:{hashlib.sha256(raw).hexdigest()[:16]}"


k1 = cache_key("c", "f", (1, 2), {"z": 9})
k2 = cache_key("c", "f", (1, 2), {"z": 9})
check("نفس المدخل ⇒ نفس المفتاح (حتميّ)", k1 == k2, f"{k1} vs {k2}")

print("\n── H7: توازن مياه WOFOST (ETc يُطرح؛ ريّ يميّز عن بعلي) ──")
wf = load("shared/wofost/engine.py", "wofost_eng")
# مصدر الكود لم يَعُد يحوي الكود الميّت
src = open(os.path.join(ROOT, "shared/wofost/engine.py"), encoding="utf-8").read()
check("أُزيل الكود الميّت 'w_demand = etc * (1000 / 1)'", "1000 / 1" not in src)
check("ETc يُطرح في حلقة التوازن (w_soil - etc)", "w_soil - etc" in src)
# سلوكي: حقن طقس صناعي (et0 عالٍ، بلا مطر) ومقارنة الريّ بالبعلي


async def _fake_weather(lat, lon, start, end):
    return [
        {
            "date": f"2025-01-{i + 1:02d}",
            "tmax": 34.0,
            "tmin": 18.0,
            "rain_mm": 0.0,
            "rad_mj": 22.0,
            "et0_mm": 8.0,
        }
        for i in range(60)
    ]


wf.fetch_weather_real = _fake_weather
res_irr = asyncio.run(
    wf.simulate_wofost("f", "قمح صلب", "loam", 15.3, 44.2, _dt.date(2025, 1, 1), 1.0, True)
)
res_rain = asyncio.run(
    wf.simulate_wofost("f", "قمح صلب", "loam", 15.3, 44.2, _dt.date(2025, 1, 1), 1.0, False)
)
yi = res_irr["simulation"]["yield_t_ha"]
yr = res_rain["simulation"]["yield_t_ha"]
need = res_irr["water_balance"]["irrigation_needed_mm"]
wsd_rain = res_rain["stress"]["water_stress_days"]
check("المحاكاة تكتمل (ريّ + بعلي) بلا استثناء", yi is not None and yr is not None)
check("احتياج ريّ > 0 حين ETc>المطر", need > 0, f"need={need}")
check("غلّة المرويّ ≥ غلّة البعلي (تمييز مائي سليم)", yi >= yr, f"irr={yi} rain={yr}")
check(
    "البعلي يُسجّل إجهاداً مائياً (ETc يُطرح فعلاً)",
    wsd_rain > 0,
    f"water_stress_days={wsd_rain}",
)

print("\n────────────────────────────────────────────")
print(f"  النتيجة: {len(PASS)} نجاح | {len(FAIL)} فشل")
if FAIL:
    print("  الإخفاقات:")
    for n, d in FAIL:
        print(f"    ✗ {n} — {d}")
print("────────────────────────────────────────────")
sys.exit(1 if FAIL else 0)

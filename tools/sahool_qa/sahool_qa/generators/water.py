"""Water investigation (0.4.0) — "was the field short of water, and why?"

  water.applied_depth        gross irrigation depth from cumulative well meters
  water.plan_vs_measured     metered irrigation against the weekly plan
  water.rain_total           rain over a window from one source
  water.rain_corroboration   is a rain event confirmed by a source of independent lineage?
  water.stress_status        FAO-56 root-zone balance: no stress / moderate / severe
  water.refill_feasibility   pumping days needed to refill that deficit at the metered well flow

The common thread is that a missing record is not a zero. A field without a
meter has unknown irrigation; a day without a rain record is not a dry day; a
plan week without a record is not a zero plan. Each of those becomes an
abstention, and the option a careless reader would pick (the sum of the records
that do exist, "0 mm", "confirmed because a second product agrees") is kept
among the distractors. A cumulative meter is the exception that teaches the
rule: its total across a gap is known, only the daily split is not.
"""

from __future__ import annotations

import hashlib
import statistics

from ..arabic import quote
from ..config import ABSTAIN_TEXT
from ..facts import tenant_key
from ..items import GenContext, bin_options, make_item
from ..waterbal import (
    DAY,
    VOLUME_PROBLEMS,
    Series,
    balance,
    coverage_problem,
    daily_increments,
    days_between,
    field_params,
    field_water,
    instrument_problem,
    inventory_for,
    kc_on,
    kc_refs,
    meter_owners,
    naive_delta,
    out_of_service,
    stress_class,
    window_delta,
)
from .common import Cards, field_ref

PROBLEMS = {
    "missing_expected_meter": "عداد ماء لبئر متوقعة مفقود بالكامل؛ الجزء المرصود ليس إجمالي ري الحقل",
    "well_inventory_missing": "لا توجد قائمة معلنة كاملة بالآبار التي تغذي الحقل؛ اكتمال مصادر الري غير معروف",
    "well_inventory_gap": "قائمة الآبار لا تغطي الفترة تغطية زمنية وحيدة كاملة",
    "well_assignment_changed": "تغير تخصيص الآبار داخل الفترة؛ يجب تقسيمها عند التغيير",
    "unassigned_meter": "عداد ماء موجود لا يطابق قائمة آبار الحقل المعلنة للفترة",
    "meter_timestamp_conflict": "قراءات مختلفة للعداد في اللحظة نفسها؛ ترتيبها غير معلوم",
    "volume_meter_stalled": "عداد الساعات تقدم وعداد الماء لم يتقدم دون سجل حالة يثبت خروج البئر من الخدمة؛ الحجم والتدفق غير معروفين",
    "hour_meter_stalled": "عداد الماء تقدم وعداد الساعات لم يتقدم؛ التدفق غير معروف",
    "well_status_conflict": "عداد الماء تقدم بينما سجل الحالة يقول إن البئر خارج الخدمة؛ التعارض يجعل الحجم غير معروف",
    "no_meter": "لا يوجد عداد آبار مسجّل لهذا الحقل؛ الري غير معروف وليس صفراً",
    "shared_meter": "العداد مسجّل لأكثر من حقل فلا يمكن قسمة حجمه بينها",
    "no_polygon": "لا توجد حدود مرسومة صالحة، والقاعدة لا تقبل المساحة المسجّلة؛ لا يمكن تحويل الحجم إلى عمق",
    "missing_endpoint": "لا توجد قراءة صالحة للعداد في أحد طرفي الفترة",
    "meter_decrease": "نزلت قراءة العداد عن سابقتها (تصفير أو استبدال) فالحجم عبرها غير معروف",
    "missing_daily_reading": "قراءة يومية للعداد مفقودة؛ المجموع عبر الفجوة معروف لكن توزيعه على الأيام غير معروف",
    "theta0_unusable": "قراءة الرطوبة الابتدائية غير صالحة (وحدة غير حجمية أو مرفوضة بفحص الجودة)",
    "missing_et0": "قيمة ET0 مفقودة ليوم أو أكثر",
    "missing_kc": "لا يوجد Kc صالح ساري في يوم أو أكثر",
    "no_complete_rain": "لا يوجد مصدر مطر مكتمل لكل أيام الفترة",
    "soil_type_missing": "قوام التربة غير مسجّل للحقل",
    "soil_type_not_in_rules": "قوام التربة المسجّل غير موجود في جدول FAO-56 المعتمد",
    "crop_missing": "المحصول غير مسجّل للحقل",
    "crop_not_in_rules": "المحصول غير موجود في جدول FAO-56 المعتمد",
    "missing_plan_week": "أسبوع من الخطة بلا سجل؛ الخطة الناقصة ليست صفراً",
    "plan_unusable": "سجل خطة غير صالح",
    "missing_rain_day": "يوم أو أكثر بلا سجل صالح من هذا المصدر؛ اليوم المفقود ليس يوماً جافاً",
    "no_pump_hours": "لا يوجد عداد ساعات تشغيل لبئر من آبار الحقل",
    "pump_hours_not_increasing": "عداد ساعات التشغيل لم يتقدم في الفترة فلا يمكن حساب التدفق",
    "no_independent_source": "لا يوجد مصدر مستقل الأصل بسجلات مكتملة لنافذة الحدث",
}

STRESS = {
    "no_stress": "لا إجهاد: العجز لم يتجاوز الماء الميسّر",
    "moderate": "إجهاد معتدل: العجز تجاوز الماء الميسّر وKs بين {ks} و1",
    "severe": "إجهاد شديد: Ks أقل من {ks}",
}
PLAN = {
    "below": "أقل من الخطة بأكثر من {tol}%",
    "within": "ضمن ±{tol}% من الخطة",
    "above": "أكثر من الخطة بأكثر من {tol}%",
}
CORR = {
    "confirmed": "مؤكَّد: مصدر مستقل الأصل سجّل مطراً يُعتدّ به في نافذة الحدث",
    "contradicted": "غير مؤكَّد: المصادر المستقلة الأصل المكتملة سجّلت النافذة دون مطر يُعتدّ به",
}
REFILL = {
    "unavailable": "لا مدة تعويض محدودة: كل آبار الحقل خارج الخدمة بسجل حالة في كل أيام الضخ من نافذة التدفق",
    "one": "أيام التشغيل اللازمة {lo:g} أو أقل",
    "few": "أيام التشغيل اللازمة أكثر من {lo:g} وحتى {hi:g}",
    "many": "أيام التشغيل اللازمة أكثر من {hi:g}",
}


def num(x: float) -> str:
    return f"{x:.6f}".rstrip("0").rstrip(".") if x is not None else "—"


def r2(x):
    return None if x is None else round(x, 2)


def wr(ctx: GenContext) -> dict:
    return ctx.rules["water"]


# ───────────────────────── shared state ─────────────────────────


def _fw(ctx: GenContext) -> dict:
    c = ctx.cache.setdefault("water", {})
    if "fw" not in c:
        c["fw"] = {k: field_water(ctx.store, f, ctx.rules) for k, f in ctx.store.fields.items()}
        c["owners"] = meter_owners(ctx.store, ctx.rules)
    return c["fw"]


def _other_owners(ctx: GenContext, f, s: Series) -> list[str]:
    _fw(ctx)
    own = ctx.cache["water"]["owners"].get((tenant_key(f.tenant), s.indicator_id), [])
    return [k for k in own if k != f.key]


def _seen(ctx: GenContext, family: str, sig) -> bool:
    """Same records under several fields (a farm gauge copied to each field): ask once."""
    seen = ctx.cache.setdefault("water_seen", {}).setdefault(family, set())
    if sig in seen:
        return True
    seen.add(sig)
    return False


def related_water(f, d) -> str:
    return "rg-" + hashlib.sha1(f"{f.key}|water|{d}".encode()).hexdigest()[:10]


# ───────────────────────── rendering ─────────────────────────


def _cell(recs, unit: str) -> str:
    parts = []
    for r in recs:
        if r.value is None:
            parts.append(
                f"مرفوض بفحص الجودة (الخام {r.qc['value']['raw']})" if "value" in r.qc else "فارغ"
            )
            continue
        t = num(r.value)
        if (r.unit or "") != unit:
            t += f" {r.unit or 'بلا وحدة'}"
        if len(recs) > 1:
            t += f" ({r.recorded_ts:%H:%M})"
        parts.append(t)
    return " / ".join(parts) if parts else "—"


def daily_table(f, cols: list[Series], a, b, title: str) -> tuple[str, list]:
    hdr = " | ".join(
        f"{s.indicator_id} ({s.unit or 'بلا وحدة'}؛ المصدر {s.source or 'غير مسجّل'})" for s in cols
    )
    lines = [
        f"{title} — سجلات field_indicators المرتبطة بالحقل [field_id={f.id}، المستأجر {f.tenant}]؛ "
        "سطر لكل يوم بالتوقيت المحلي؛ «—» = لا يوجد سجل",
        "الأعمدة: " + hdr,
    ]
    for d in days_between(a, b):
        lines.append(f"{d}: " + " | ".join(_cell(s.records.get(d, []), s.unit) for s in cols))
    return "\n".join(lines), [r for s in cols for r in s.between(a, b)]


def kc_lines(f, s: Series, upto) -> tuple[str, list]:
    recs = [r for d in s.days() if d <= upto for r in s.records[d]]
    body = "؛ ".join(f"{r.recorded_at}: {_cell([r], s.unit)}" for r in recs) or "لا توجد سجلات"
    return (
        f"سجلات {s.indicator_id} للحقل [field_id={f.id}] (تسري القيمة من تاريخها حتى السجل التالي): {body}",
        recs,
    )


AREA_RULE = (
    "المساحة جيوديسية على إهليلج WGS84 من الحدود المرسومة فقط (لا تُقبل المساحة المسجّلة، والحقل بلا حدود "
    "صالحة لا يُحسب له عمق)"
)


STALL_TEXT = (
    "إذا تقدم عداد ساعات البئر ساعة أو أكثر بين قراءتي نهاية يومين (آخر قراءة صالحة في كل يوم) بينما لم "
    "يتقدم عداد مائها بينهما، ولا يوجد سجل حالة (well_status) بقيمة 0 في كل أيام الضخ بينهما، فهذا تعارض بين "
    "العدادين: لا يُعرف أهو عداد متوقف أم بئر جافة أم صمام مغلق، فالحجم والتدفق غير معروفين، ولا يُعدّان صفراً"
)
PUMP_DAYS_TEXT = (
    "أيام الضخ بين قراءتي نهاية يومين هي من اليوم التالي للأولى حتى يوم الثانية؛ فيوم القراءة الأولى نفسه "
    "ليس منها"
)
_RANGE_LABELS = (
    ("rain", "المطر", "مم"),
    ("et0", "ET0", "مم"),
    ("kc", "Kc", ""),
    ("soil_moisture", "الرطوبة", "m3/m3"),
    ("meter", "عداد الماء", "م³"),
    ("pump_hours", "عداد الساعات", "ساعة"),
    ("plan_week", "الخطة", "مم"),
    ("well_status", "حالة البئر", ""),
)


def valid_text(rules: dict) -> str:
    rng = rules.get("water_ranges", {})

    def n(x):
        return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:g}"

    parts = [
        (
            f"{label} {n(rng[k][0])} أو {n(rng[k][1])}"
            if k == "well_status"
            else f"{label} {n(rng[k][0])} إلى {n(rng[k][1])} {unit}".strip()
        )
        for k, label, unit in _RANGE_LABELS
        if k in rng
    ]
    return (
        "القراءة الصالحة = سجل اجتاز فحص الجودة: وحدة مقبولة لنوعه وقيمة ضمن مداه بعد التحويل ("
        + "، ".join(parts)
        + ")"
    )


def depth_rule(rules: dict | None = None) -> str:
    from ..config import DEFAULT_RULES

    rules = rules or DEFAULT_RULES
    return (
        "قاعدة عمق الري: العداد تراكمي، وقراءة اليوم = آخر قراءة صالحة فيه وتمثل نهاية ذلك اليوم؛ فالحجم بين نهاية يوم a "
        "ونهاية يوم b (ضخ الأيام من اليوم التالي لـa حتى b) = قراءة b − قراءة a، ولو غابت القراءات بينهما. إذا نزلت "
        "قراءة عن سابقتها بين طرفي الفترة (تصفير أو استبدال) فالحجم للفترة غير معروف، ولو أمكن حساب حدٍّ أدنى له؛ ولا "
        "يؤثر نزول خارجها. تُفحص جميع القراءات داخل الفترة، بما فيها قراءات اليوم الواحد. "
        "لا يُحسب الإجمالي دون قائمة آبار كاملة سارية لكل الفترة ومطابقة للعدادات؛ تغير تخصيص الآبار يستلزم تقسيم الفترة. العمق الإجمالي (مم) = "
        f"مجموع حجوم عدادات الحقل (م³) ÷ مساحة الحقل (م²) × 1000؛ {AREA_RULE}. العداد المسجّل لأكثر من حقل: حصة كل "
        "حقل منه غير معروفة، فلا يُحسب عمق لأيٍّ منها. والحقل الذي لا عداد له ريّه غير معروف لا صفر؛ أما عداد قُرئ ولم "
        "يتقدم فريّه صفر معروف، ما لم يتقدم عداد ساعات البئر نفسها. "
        f"{STALL_TEXT}. {PUMP_DAYS_TEXT}. {valid_text(rules)}. النطاق «x-y» يشمل x ولا يشمل y"
    )


def stress_rule(ctx: GenContext, prm: dict | None, f) -> str:
    w = wr(ctx)
    if prm:
        p_lines = [
            f"- المعاملات لقوام التربة {prm['soil']} والمحصول {prm['crop']}: θFC وθWP منتصف المدى في FAO-56 "
            "الجدول 19، وZr الحد الأدنى في الجدول 22 (للجدولة)، وp الجدولية من الجدول نفسه، وEa افتراض سهول:",
            f"θFC = {prm['fc']:g} m3/m3",
            f"θWP = {prm['wp']:g} m3/m3",
            f"Zr = {prm['zr']:g} m",
            f"p_table = {prm['p_table']:g}",
            f"Ea = {prm['ea']:g}",
            f"fao_crop = {prm['fao_crop']}",
        ]
    else:
        p_lines = [
            f"- المعاملات: θFC وθWP من منتصف مدى FAO-56 الجدول 19 بحسب قوام التربة المسجّل للحقل "
            f"({f.soil_type or 'غير مسجّل'})، وZr الأدنى وp من الجدول 22 بحسب المحصول ({f.crop or 'غير مسجّل'})",
            f"Ea = {w['application_efficiency']:g}",
        ]
    ks = w["ks_severe"]
    order = " ثم ".join(w["rain_priority"])
    return "\n".join(
        [
            "قاعدة موازنة الماء في المنطقة الجذرية (FAO-56، الفصل 8):",
            *p_lines,
            "- المعادلات التالية تستخدم عجز بداية اليوم لحساب Ks:",
            "TAW = 1000 × (θFC − θWP) × Zr",
            "ETc = Kc × ET0",
            "p = min(0.8, max(0.1, p_table + 0.04 × (5 − ETc)))",
            "RAW = p × TAW",
            "Dr0 = min(TAW, max(0, 1000 × (θFC − θ0) × Zr))",
            "- Dr0 عجز نهاية يوم قراءة الرطوبة، والموازنة تبدأ من اليوم التالي. θ0 قراءة المجس الحجمية كما سُجّلت، وتُعامل "
            "متوسطاً للمنطقة الجذرية كلها أياً كان عمق المجس (افتراض سهول)؛ ومتوسطها إن تعددت في اليوم. "
            "النسبة المئوية تُقسم على 100، وm3/m3 تؤخذ مباشرة؛ أي وحدة أخرى لا تصلح",
            "Ks = 1  [Dr_start ≤ RAW]",
            "Ks = (TAW − Dr_start) / ((1 − p) × TAW)  [Dr_start > RAW]",
            "I_net = Ea × I_gross",
            "ET_actual = min(Ks × ETc, max(0, TAW − Dr_start + P + I_net))",
            "DP = max(0, P + I_net − ET_actual − Dr_start)",
            "Dr_end = Dr_start − P − I_net + ET_actual + DP",
            "- الاستخراج لا يتجاوز الماء المتاح فوق نقطة الذبول؛ الفائض تسرب عميق؛ الجريان السطحي والصعود الشعري صفر",
            "- الري الإجمالي ليوم (مم) = مجموع فروق قراءات عدادات الحقل بين نهاية اليوم السابق ونهاية اليوم ÷ المساحة (م²) × "
            f"1000؛ قراءة اليوم = آخر قراءة صالحة فيه؛ {AREA_RULE}",
            "- عند تعدد سجلات يوم واحد: ET0 والمطر والرطوبة بمتوسطها اليومي، وعداد الماء بآخر قراءة صالحة في اليوم",
            f"- Kc ساري من تاريخ سجله حتى السجل التالي؛ المطر من أول مصدر سجلاته مكتملة لكل أيام الموازنة (من اليوم التالي "
            f"لقراءة الرطوبة حتى اليوم المسؤول عنه)، بالترتيب: {order}",
            "- حالة نهاية اليوم المسؤول عنه: لا إجهاد إذا لم يتجاوز عجز نهايته RAW ذلك اليوم (بـp ذلك اليوم)؛ وإلا نحسب "
            "المعامل التالي بـp ذلك اليوم:",
            "Ks_end = (TAW − Dr_end) / ((1 − p) × TAW)",
            f"- بعد تجاوز الماء الميسّر: الإجهاد معتدل إذا بلغ معامل نهاية اليوم {ks:g} أو أكثر، وشديد إذا قل عنه.",
            "- تُفحص جميع قراءات العداد داخل الفترة، ويلزم سجل كامل لتخصيص الآبار لكل الفترة ومطابق للعدادات.",
            f"- {STALL_TEXT}. {PUMP_DAYS_TEXT}.",
            f"- {valid_text(ctx.rules)}.",
            "- يوم بلا ET0، أو بلا مطر من المصدر المختار، أو يوم غابت فيه قراءة عداد واحد من عدادات الحقل ولو قُرئ غيره — حتى لو كان مجموع العداد التراكمي "
            "عبر الفجوة معروفاً، لأن توزيعه على الأيام غير معروف — أو عداد نزلت قراءته، أو حقل بلا عداد أو عداده مشترك مع حقل "
            "آخر: كل ذلك يجعل الحالة غير معروفة؛ السجل المفقود ليس صفراً",
        ]
    )


def lineage_text(ctx: GenContext) -> str:
    src = wr(ctx)["rain_sources"]
    return "؛ ".join(f"{k} ({v['label']}): {'+'.join(v['lineage'])}" for k, v in src.items())


def corroboration_rule(ctx: GenContext) -> str:
    w = wr(ctx)
    return (
        f"قاعدة تأكيد المطر: الحدث = يوم سجّل فيه مصدر {w['rain_event_mm']:g} مم أو أكثر. يتأكد إذا سجّل مصدر آخر "
        f"مستقل الأصل (لا يشترك معه في أي أصل) {w['rain_confirm_mm']:g} مم أو أكثر في مجموع الأيام "
        + (
            "من اليوم السابق له إلى اليوم التالي"
            if w["rain_window_days"] == 1
            else f"من {w['rain_window_days']} أيام قبله إلى {w['rain_window_days']} أيام بعده"
        )
        + "، بشرط أن تكون سجلاته في تلك الأيام كاملة؛ ولا يتأكد إذا سجّلت المصادر المستقلة المكتملة كلها أقل من ذلك؛ وإذا لم يوجد مصدر مستقل مكتمل فلا يمكن "
        "الحكم. اتفاق مصدرين من الأصل نفسه ليس تأكيداً. عند تعدد سجلات مصدر في يوم واحد تُستخدم قيمتها اليومية المتوسطة. "
        "أصل التوقيت اليومي لكل مصدر: " + lineage_text(ctx)
    )


# ───────────────────────── irrigation from meters ─────────────────────────


def irrigation_window(ctx, fw, a, b) -> dict:
    """Gross depth over [a, b]. Returns {"depth"} or {"problem", "naive", "detail"}."""
    f = fw.field
    meters = list(fw.of("meter").values())
    if not meters:
        return {"problem": "no_meter", "naive": 0.0}
    prob, detail = coverage_problem(ctx.store, fw, ctx.rules, a, b)
    vols, naive_vol = [], 0.0
    for sx, s in fw.of("meter").items():
        dv, p = window_delta(s, a, b)
        naive_vol += naive_delta(s, a, b)
        if p and not prob:
            prob, detail = p, s.indicator_id
        if not prob:
            ip, idet = instrument_problem(fw, sx, a, b, ctx.rules)
            if ip in VOLUME_PROBLEMS:  # a stalled hour meter does not touch the volume
                prob, detail = ip, idet
        vols.append(dv)
    others = sorted({k for s in meters for k in _other_owners(ctx, f, s)})
    area = f.geom.area_m2 if f.geom is not None else None
    naive_area = area or (f.area_ha_stored * 1e4 if f.area_ha_stored else None)
    naive = None if naive_area is None else naive_vol / naive_area * 1000
    if others:
        return {"problem": "shared_meter", "naive": naive, "detail": others}
    if area is None:
        return {"problem": "no_polygon", "naive": naive}
    if prob:
        return {"problem": prob, "naive": naive, "detail": detail}
    return {"depth": sum(vols) / area * 1000, "volume_m3": sum(vols), "area_m2": area}


def irrigation_daily(ctx, fw, a, b) -> tuple[dict | None, str | None, object]:
    f = fw.field
    meters = list(fw.of("meter").values())
    if not meters:
        return None, "no_meter", None
    others = sorted({k for s in meters for k in _other_owners(ctx, f, s)})
    if others:
        return None, "shared_meter", others
    if f.geom is None:
        return None, "no_polygon", None
    area = f.geom.area_m2
    problem, detail = coverage_problem(ctx.store, fw, ctx.rules, a, b)
    if problem:
        return None, problem, detail
    total = {d: 0.0 for d in days_between(a + DAY, b)}
    for sx, s in fw.of("meter").items():
        inc, prob, at = daily_increments(s, a, b)
        if prob:
            return None, prob, f"{s.indicator_id} {at}"
        ip, idet = instrument_problem(fw, sx, a, b, ctx.rules)
        if ip in VOLUME_PROBLEMS:
            return None, ip, idet
        for d, vol in inc.items():
            total[d] += vol / area * 1000
    return total, None, None


def _status_cards(f, fw, upto, cards: Cards):
    """Well status records are step records: those before the window still hold, so list all up to its end."""
    for s in fw.of("well_status").values():
        t, recs = kc_lines(f, s, upto)
        cards.table(t, recs)
    if (fw.of("meter") or fw.of("pump_hours")) and not fw.of("well_status"):
        cards.text(f"لا توجد سجلات حالة آبار (well_status_*) للحقل [field_id={f.id}]")


def _meter_cards(f, fw, a, b, cards: Cards, title="قراءات عدادات الآبار"):
    """Both meters of every well (the hour meter is needed to see a stalled volume meter) and the status log."""
    cols = list(fw.of("meter").values()) + list(fw.of("pump_hours").values())
    if cols:
        t, recs = daily_table(f, cols, a, b, title + " (الماء والساعات)")
        cards.table(t, recs)
    if not fw.of("meter"):
        cards.text(
            f"{title}: لا توجد في المنصة سجلات meter_total_* مرتبطة بالحقل [field_id={f.id}]"
        )
    _status_cards(f, fw, b, cards)


def _meter_refs(fw, a, b) -> list[dict]:
    """Evidence references for every record the meter rules read: both meters, and status records in force."""
    refs = [s.ref(a, b) for k in ("meter", "pump_hours") for s in fw.of(k).values()]
    for s in fw.of("well_status").values():
        days = [x for x in s.days() if x <= b]
        if days:
            refs.append(s.ref(days[0], b))
    return refs


def _shared_note(ctx, f, fw, cards: Cards) -> list[str]:
    refs = []
    inv = inventory_for(ctx.store, f, ctx.rules)
    if inv is None:
        cards.text("قائمة آبار الحقل الكاملة غير متاحة؛ اكتمال مصادر الري غير معروف")
    else:
        for v in inv:
            cards.text(
                f"قائمة الآبار الكاملة للحقل [field_id={f.id}، المستأجر {f.tenant}] من {v['from']} إلى {v['to']} "
                f"شاملين الطرفين: {', '.join(v['wells']) or 'لا آبار معلنة'}"
            )
    missing = set(fw.of("pump_hours")) - set(fw.of("meter"))
    if missing:
        cards.text("توجد سجلات ساعات بلا عداد ماء مقابل: " + ", ".join(sorted(missing)))
    for s in fw.of("meter").values():
        for k in _other_owners(ctx, f, s):
            o = ctx.store.fields[k]
            cards.text(
                f"العداد {s.indicator_id} مسجّل أيضاً للحقل {quote(o.display)} [field_id={o.id}]"
            )
            refs.append(k)
    return refs


def _bins(value: float, rng, rules_w):
    """Three consecutive ranges (no isolated range can give the answer away) + the abstain option."""
    return bin_options(
        value, rules_w["depth_rel_width"], "مم", rng, min_width=rules_w["depth_min_width_mm"], n=3
    )


# ───────────────────────── families ─────────────────────────

WINDOW_FREE = {
    "no_meter",
    "shared_meter",
    "no_polygon",
    "well_inventory_missing",
    "missing_expected_meter",
}


def gen_applied_depth(ctx: GenContext):
    """Whole metered span plus each 7-day window inside it."""
    fam = "water.applied_depth"
    w = wr(ctx)
    for fk, fw in _fw(ctx).items():
        if not fw.has_any():
            continue
        f = fw.field
        meters = list(fw.of("meter").values())
        days = sorted({d for s in meters for d in s.days()}) if meters else fw.all_days()
        a0, b0 = days[0], days[-1]
        if a0 == b0:
            ctx.skip(fam, "single_day")
            continue
        windows = [(a0, b0)] + [
            (a0 + 7 * k * DAY, a0 + 7 * (k + 1) * DAY)
            for k in range((b0 - a0).days // 7)
            if (b0 - a0).days > 7
        ]
        asked_values = set()
        for a, b in windows:
            res = irrigation_window(ctx, fw, a, b)
            if res.get("problem") in WINDOW_FREE and (a, b) != (a0, b0):
                ctx.skip(fam, "same_reason_as_whole_span")
                continue
            if "depth" in res:
                if (
                    round(res["depth"], 1) in asked_values
                ):  # steady pumping: the same week again tests nothing new
                    ctx.skip(fam, "same_value_as_another_window")
                    continue
                asked_values.add(round(res["depth"], 1))
            cards = Cards().field(f, True).text(depth_rule(ctx.rules))
            _meter_cards(f, fw, a, b, cards)
            refs = _shared_note(ctx, f, fw, cards)
            rng = ctx.rng(f"{fam}:{fk}:{a}:{b}")
            if "depth" in res:
                correct, distractors, meta = _bins(res["depth"], rng, w)
                distractors = distractors + [ABSTAIN_TEXT]
                answerable, val = True, round(res["depth"], 2)
            else:
                if res["naive"] is None:
                    ctx.skip(fam, "no_area_for_options")
                    continue
                naive_bin, others, meta = _bins(res["naive"], rng, w)
                correct, answerable, val = None, False, None
                distractors = [naive_bin] + others  # the careless reading's range is always offered
            it = make_item(
                ctx,
                family=fam,
                level="scene_understanding",
                question=(
                    f"ما عمق الري الإجمالي الذي أُضيف إلى الحقل {quote(f.display)} بين نهاية يوم {a} ونهاية يوم {b} "
                    "وفق سجلات المنصة؟"
                ),
                correct=correct,
                distractors=distractors,
                answerable=answerable,
                allow_abstain=False,
                evidence={
                    "kind": "derived",
                    "records": [field_ref(f)] + _meter_refs(fw, a, b),
                    "values": {
                        "window": [str(a), str(b)],
                        **{k: (r2(v) if isinstance(v, float) else v) for k, v in res.items()},
                        **meta,
                    },
                    "rule": depth_rule(ctx.rules),
                    "computation": (
                        "فرق قراءتي طرفي الفترة لكل عداد ← مجموعها ÷ مساحة المضلع × 1000"
                        if answerable
                        else PROBLEMS[res["problem"]]
                    ),
                    "caveats": [
                        "العمق إجمالي عند العداد؛ الماء الذي يبلغ الجذور أقل منه بحسب كفاءة الإضافة"
                    ],
                },
                context=cards,
                key={"field": fk, "from": str(a), "to": str(b)},
                field_refs=refs,
                answer_value=val,
            )
            if it:
                yield it


def plan_rule(ctx) -> str:
    w = wr(ctx)
    tol = int(round(100 * w["plan_tolerance_rel"]))
    return (
        f"قاعدة مقارنة الخطة: سجل الخطة الأسبوعية (irrigation_plan_week) = العمق الإجمالي المخطط (مم) لسبعة أيام أولها "
        f"تاريخ السجل وآخرها بعده بستة أيام؛ أسبوع بلا سجل يجعل الخطة غير معروفة (ليست صفراً). المقيس = عمق ضخ الأيام "
        f"نفسها من عدادات الآبار: من نهاية اليوم السابق لأول يوم حتى نهاية آخر يوم (قاعدة عمق الري). النسبة = المقيس ÷ "
        f"المخطط: أقل من {1 - tol / 100:g} ← أقل من الخطة؛ أكثر من {1 + tol / 100:g} ← أكثر من الخطة؛ وإلا ضمن ±{tol}%"
    )


def gen_plan_vs_measured(ctx: GenContext):
    fam = "water.plan_vs_measured"
    w = wr(ctx)
    tol, mg = w["plan_tolerance_rel"], w["plan_margin_rel"]
    labels = {k: v.format(tol=int(round(100 * tol))) for k, v in PLAN.items()}
    for fk, fw in _fw(ctx).items():
        f = fw.field
        for ps in fw.of("plan_week").values():
            weeks = ps.days()
            a, b = (
                weeks[0] - DAY,
                weeks[-1] + 6 * DAY,
            )  # end-of-day readings bracketing the planned days
            problem = None
            if any((y - x).days != 7 for x, y in zip(weeks, weeks[1:], strict=False)):
                problem = "missing_plan_week"
            elif any(ps.value(d) is None for d in weeks):
                problem = "plan_unusable"
            planned = sum(ps.value(d) or 0.0 for d in weeks)
            res = irrigation_window(ctx, fw, a, b)
            problem = problem or res.get("problem")
            cls = ratio = None
            if problem is None:
                if planned <= 0:
                    ctx.skip(fam, "zero_plan")
                    continue
                ratio = res["depth"] / planned
                if min(abs(ratio - (1 - tol)), abs(ratio - (1 + tol))) < mg:
                    ctx.skip(fam, "ratio_near_threshold")
                    continue
                cls = "below" if ratio < 1 - tol else "above" if ratio > 1 + tol else "within"
            cards = Cards().field(f, True).text(plan_rule(ctx)).text(depth_rule(ctx.rules))
            t, recs = daily_table(f, [ps], weeks[0], weeks[-1], "سجلات الخطة الأسبوعية")
            cards.table(t, recs)
            _meter_cards(f, fw, a, b, cards)
            refs = _shared_note(ctx, f, fw, cards)
            it = make_item(
                ctx,
                family=fam,
                level="scene_reasoning",
                question=(
                    f"كيف يقارن الري الذي سجّلته عدادات آبار الحقل {quote(f.display)} بخطة الري الأسبوعية للأيام من "
                    f"{weeks[0]} إلى {b} شاملةً؟"
                ),
                correct=None if problem else labels[cls],
                answerable=problem is None,
                allow_abstain=False,
                distractors=[labels[k] for k in PLAN if k != cls]
                + ([] if problem else [ABSTAIN_TEXT]),
                evidence={
                    "kind": "derived",
                    "records": [field_ref(f), ps.ref()] + _meter_refs(fw, a, b),
                    "values": {
                        "window": [str(a), str(b)],
                        "planned_mm": r2(planned),
                        "measured_mm": r2(res.get("depth")),
                        "ratio": None if ratio is None else round(ratio, 4),
                        "class": cls,
                        "problem": problem,
                    },
                    "rule": plan_rule(ctx),
                    "computation": (
                        "مجموع الخطة ← عمق العدادات للفترة نفسها ← النسبة ← الفئة"
                        if problem is None
                        else PROBLEMS[problem]
                    ),
                },
                context=cards,
                key={"field": fk, "plan": ps.indicator_id, "from": str(a), "to": str(b)},
                field_refs=refs,
                answer_value=cls,
            )
            if it:
                yield it


def rain_rule() -> str:
    return (
        "قاعدة مجموع المطر: مجموع القيم اليومية للمصدر المذكور في كل أيام الفترة شاملةً طرفيها؛ عند تعدد السجلات في "
        "اليوم تُستخدم قيمتها اليومية المتوسطة؛ يوم بلا سجل صالح يجعل المجموع غير معروف (ليس يوماً جافاً). النطاق «أ-ب» "
        "يشمل أ ولا يشمل ب"
    )


def gen_rain_total(ctx: GenContext):
    fam = "water.rain_total"
    w = wr(ctx)
    for fk, fw in _fw(ctx).items():
        f = fw.field
        rain = list(fw.of("rain").values())
        if not rain:
            continue
        span = sorted({d for s in rain for d in s.days()})
        a, b = span[0], span[-1]
        for s in rain:
            vals = {d: s.value(d) for d in days_between(a, b)}
            sig = (
                tenant_key(f.tenant),
                s.indicator_id.lower(),
                str(a),
                str(b),
                tuple(sorted(vals.items())),
            )
            if _seen(ctx, fam, sig):
                ctx.skip(fam, "same_records_as_another_field")
                continue
            missing = [d for d, x in vals.items() if x is None]
            total = sum(x for x in vals.values() if x is not None)
            rng = ctx.rng(f"{fam}:{fk}:{s.indicator_id}")
            correct, others, meta = bin_options(
                total, 0.25, "مم", rng, min_width=w["depth_min_width_mm"], n=3
            )
            t, recs = daily_table(f, [s], a, b, f"سجلات {s.indicator_id}")
            it = make_item(
                ctx,
                family=fam,
                level="object_understanding",
                question=f"ما مجموع المطر في الحقل {quote(f.display)} من {a} إلى {b} شاملةً وفق سجلات {s.indicator_id}؟",
                correct=None if missing else correct,
                answerable=not missing,
                allow_abstain=False,
                distractors=([correct] + others) if missing else (others + [ABSTAIN_TEXT]),
                evidence={
                    "kind": "derived",
                    "records": [field_ref(f), s.ref(a, b)],
                    "values": {
                        "window": [str(a), str(b)],
                        "total_mm": None if missing else r2(total),
                        "missing_days": [str(d) for d in missing],
                        "sum_of_recorded_days_mm": r2(total),
                        **meta,
                    },
                    "rule": rain_rule(),
                    "computation": "جمع القيم اليومية"
                    if not missing
                    else PROBLEMS["missing_rain_day"],
                    "caveats": (
                        []
                        if "station" in s.indicator_id.lower()
                        else ["منتجات الأقمار والتحليل تقدير شبكي لا قياس في الحقل"]
                    ),
                },
                context=Cards().field(f).table(t, recs).text(rain_rule()),
                key={"field": fk, "series": s.indicator_id, "from": str(a), "to": str(b)},
                answer_value=None if missing else r2(total),
            )
            if it:
                yield it


def gen_rain_corroboration(ctx: GenContext):
    fam = "water.rain_corroboration"
    w = wr(ctx)
    src_cfg = w["rain_sources"]
    win = w["rain_window_days"]
    for fk, fw in _fw(ctx).items():
        f = fw.field
        rain = {sx: s for sx, s in fw.of("rain").items() if sx in src_cfg}
        if len(rain) < 2:
            continue
        asked = []
        for sx in reversed(w["rain_priority"]):
            s = rain.get(sx)
            if s is None:
                continue
            for d in s.usable_days():
                v = s.value(d)
                if v < w["rain_event_mm"] or any(abs((d - x).days) <= win for x in asked):
                    continue
                a, b = d - win * DAY, d + win * DAY
                rows, verdicts = {}, []
                for tx, ts in rain.items():
                    if tx == sx:
                        continue
                    indep = not set(src_cfg[tx]["lineage"]) & set(src_cfg[sx]["lineage"])
                    vals = [ts.value(x) for x in days_between(a, b)]
                    complete = all(x is not None for x in vals)
                    tot = sum(x for x in vals if x is not None)
                    rows[tx] = {
                        "independent": indep,
                        "complete": complete,
                        "window_total_mm": r2(tot),
                    }
                    if indep and complete:
                        verdicts.append(tot)
                if any(abs(t - w["rain_confirm_mm"]) < w["rain_margin_mm"] for t in verdicts):
                    ctx.skip(fam, "total_near_threshold")
                    continue
                cls = (
                    None
                    if not verdicts
                    else "confirmed"
                    if any(t >= w["rain_confirm_mm"] for t in verdicts)
                    else "contradicted"
                )
                cols = [rain[x] for x in rain]
                sig = (
                    tenant_key(f.tenant),
                    sx,
                    str(d),
                    tuple(
                        (c.indicator_id, tuple(c.value(x) for x in days_between(a, b)))
                        for c in cols
                    ),
                )
                asked.append(d)
                if _seen(ctx, fam, sig):
                    ctx.skip(fam, "same_records_as_another_field")
                    continue
                t, recs = daily_table(f, cols, a, b, "سجلات المطر من كل المصادر")
                it = make_item(
                    ctx,
                    family=fam,
                    level="scene_reasoning",
                    question=(
                        f"سجّل {s.indicator_id} مطراً قدره {num(v)} مم في الحقل {quote(f.display)} يوم {d}. "
                        "هل يؤكد هذا الهطولَ مصدرٌ مستقل الأصل وفق قاعدة التأكيد في سهول؟"
                    ),
                    correct=None if cls is None else CORR[cls],
                    answerable=cls is not None,
                    allow_abstain=False,
                    distractors=[CORR[k] for k in ("confirmed", "contradicted") if k != cls]
                    + ([] if cls is None else [ABSTAIN_TEXT]),
                    evidence={
                        "kind": "derived",
                        "records": [field_ref(f)] + [c.ref(a, b) for c in cols],
                        "values": {
                            "event": {"source": sx, "date": str(d), "mm": r2(v)},
                            "window": [str(a), str(b)],
                            "others": rows,
                            "class": cls,
                        },
                        "rule": corroboration_rule(ctx),
                        "computation": (
                            "مجموع كل مصدر آخر في النافذة ← استبعاد غير المستقل وغير المكتمل ← المقارنة "
                            "بالعتبة"
                            if cls
                            else PROBLEMS["no_independent_source"]
                        ),
                        "caveats": [
                            "الاستقلال هنا في أصل التوقيت اليومي؛ CHIRPS يستخدم محطات وأقماراً في مجاميعه "
                            "الخماسية، لكن توزيعها على الأيام من ERA5"
                        ],
                    },
                    context=Cards().field(f).table(t, recs).text(corroboration_rule(ctx)),
                    key={"field": fk, "source": sx, "date": str(d)},
                    answer_value=cls,
                )
                if it:
                    yield it


# ───────────────────────── FAO-56 balance ─────────────────────────


def _stress_case(ctx, fw, d0, D) -> dict:
    f, w = fw.field, wr(ctx)
    case = {"field": f, "fw": fw, "d0": d0, "d": D}
    prm, prob = field_params(f, ctx.rules)
    case["prm"] = prm
    if prob:
        return {**case, "problem": prob}
    vals = [s.value(d0) for s in fw.of("soil_moisture").values()]
    usable = [x for x in vals if x is not None]
    if not usable:
        return {**case, "problem": "theta0_unusable"}
    theta0 = statistics.fmean(usable)
    days = days_between(d0 + DAY, D)
    et0s, kcs = list(fw.of("et0").values()), list(fw.of("kc").values())
    if len(et0s) > 1 or len(kcs) > 1:
        return {**case, "skip": "several_et0_or_kc_series"}
    if not et0s or any(et0s[0].value(d) is None for d in days):
        return {**case, "problem": "missing_et0"}
    if not kcs or any(kc_on(kcs[0], d) is None for d in days):
        return {**case, "problem": "missing_kc"}
    et0 = {d: et0s[0].value(d) for d in days}
    kc = {d: kc_on(kcs[0], d) for d in days}
    src = next(
        (
            sx
            for sx in w["rain_priority"]
            if sx in fw.of("rain") and all(fw.of("rain")[sx].value(d) is not None for d in days)
        ),
        None,
    )
    if src is None:
        return {**case, "problem": "no_complete_rain"}
    rain = {d: fw.of("rain")[src].value(d) for d in days}
    if max(rain.values()) > w["runoff_free_max_mm"]:
        return {**case, "skip": "runoff_not_modelled"}
    irr, prob, detail = irrigation_daily(ctx, fw, d0, D)
    if prob:
        return {**case, "problem": prob, "detail": detail}
    dr0, rows = balance(prm, theta0, days, et0, kc, rain, irr)
    last = rows[-1]
    cls, ks = stress_class(last["dr_end"], last["raw"], prm["taw"], last["p"], ctx.rules)
    out = {
        **case,
        "class": cls,
        "ks_end": ks,
        "dr": last["dr_end"],
        "raw": last["raw"],
        "p": last["p"],
        "rows": rows,
        "rain_source": src,
        "theta0": theta0,
        "dr0": dr0,
    }
    if abs(last["dr_end"] - last["raw"]) < w["stress_margin_mm"]:
        out["near"] = "deficit_near_raw"
    elif cls != "no_stress" and abs(ks - w["ks_severe"]) < w["ks_margin"]:
        out["near"] = "ks_near_threshold"
    return out


# problems that do not depend on the day asked
STATIC_PROBLEMS = {
    "well_inventory_missing",
    "missing_expected_meter",
    "no_meter",
    "shared_meter",
    "no_polygon",
    "theta0_unusable",
    "soil_type_missing",
    "soil_type_not_in_rules",
    "crop_missing",
    "crop_not_in_rules",
}


def stress_cases(ctx: GenContext) -> list[dict]:
    c = ctx.cache.setdefault("water", {})
    if "stress" in c:
        return c["stress"]
    step = wr(ctx)["check_every_days"] * DAY
    out = []
    for _fk, fw in _fw(ctx).items():
        sm = fw.of("soil_moisture")
        if not sm:
            continue
        starts = sorted({d for s in sm.values() for d in s.days()})
        end_all = fw.all_days()[-1]
        for i, d0 in enumerate(starts):
            horizon = starts[i + 1] - DAY if i + 1 < len(starts) else end_all
            D = d0 + step
            while D <= horizon:
                case = _stress_case(ctx, fw, d0, D)
                out.append(case)
                if case.get("problem") in STATIC_PROBLEMS:
                    break  # the same reason on every later day: ask once
                D += step
    c["stress"] = out
    return out


def _balance_cards(ctx, case, extra_kinds=()) -> tuple[Cards, list[str]]:
    f, fw, d0, D = case["field"], case["fw"], case["d0"], case["d"]
    cards = Cards().field(f, True).text(stress_rule(ctx, case.get("prm"), f))
    cols = (
        list(fw.of("soil_moisture").values())
        + list(fw.of("et0").values())
        + list(fw.of("rain").values())
        + list(fw.of("meter").values())
        + list(fw.of("pump_hours").values())
    )
    t, recs = daily_table(f, cols, d0, D, "السجلات اليومية")
    cards.table(t, recs)
    if not fw.of("meter"):
        cards.text(f"لا توجد في المنصة سجلات meter_total_* مرتبطة بالحقل [field_id={f.id}]")
    _status_cards(f, fw, D, cards)
    for s in fw.of("kc").values():
        t, recs = kc_lines(f, s, D)
        cards.table(t, recs)
    if not fw.of("kc"):
        cards.text(f"لا توجد سجلات Kc للحقل [field_id={f.id}]")
    refs = _shared_note(ctx, f, fw, cards)
    return cards, refs


def _kc_evidence(case):
    return [
        ref for s in case["fw"].of("kc").values() for ref in kc_refs(s, case["d0"] + DAY, case["d"])
    ]


def _balance_values(case) -> dict:
    if "rows" not in case:
        return {
            "problem": case.get("problem"),
            "detail": case.get("detail"),
            "params": case.get("prm"),
        }
    return {
        "params": case["prm"],
        "theta0": round(case["theta0"], 4),
        "dr0_mm": r2(case["dr0"]),
        "rain_source": case["rain_source"],
        "dr_end_mm": r2(case["dr"]),
        "raw_mm": r2(case["raw"]),
        "p_end": round(case["p"], 4),
        "ks_end": round(case["ks_end"], 4),
        "class": case.get("class"),
        "daily": [
            {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}
            for r in case["rows"]
        ],
    }


BALANCE_CAVEATS = [
    "Zr ثابت عند الحد الأدنى لعمق الجذور الأقصى؛ الجذور أقصر في بداية الموسم",
    "θFC وθWP قيم نموذجية لقوام التربة لا قياس حقلي، وEa افتراض",
    "قراءة الرطوبة من مجس واحد تُعامل كأنها تمثل المنطقة الجذرية كلها",
    "الحالة نتيجة نموذج؛ تأكيدها ميدانياً بمجس رطوبة أو بقياس جهد ماء الورقة",
]


def gen_stress_status(ctx: GenContext):
    fam = "water.stress_status"
    ks = wr(ctx)["ks_severe"]
    labels = {k: v.format(ks=f"{ks:g}") for k, v in STRESS.items()}
    for case in stress_cases(ctx):
        if case.get("skip") or case.get("near"):
            ctx.skip(fam, case.get("skip") or case["near"])
            continue
        f, D = case["field"], case["d"]
        cls = case.get("class")
        answerable = "problem" not in case
        cards, refs = _balance_cards(ctx, case)
        it = make_item(
            ctx,
            family=fam,
            level="scene_reasoning",
            question=(
                f"وفق موازنة الماء في المنطقة الجذرية (FAO-56) المحسوبة من سجلات المنصة منذ قراءة الرطوبة في "
                f"{case['d0']}، ما حالة الماء في جذور الحقل {quote(f.display)} في نهاية يوم {D}؟"
            ),
            correct=labels[cls] if answerable else None,
            answerable=answerable,
            allow_abstain=False,
            distractors=[labels[k] for k in STRESS if k != cls]
            + ([ABSTAIN_TEXT] if answerable else []),
            evidence={
                "kind": "derived",
                "records": [field_ref(f)]
                + [
                    s.ref(case["d0"], D)
                    for k in ("soil_moisture", "et0", "rain")
                    for s in case["fw"].of(k).values()
                ]
                + _meter_refs(case["fw"], case["d0"], D)
                + _kc_evidence(case),
                "values": _balance_values(case),
                "rule": stress_rule(ctx, case.get("prm"), f),
                "computation": (
                    "Dr0 من الرطوبة ← موازنة يومية ← مقارنة Dr بـRAW ثم Ks بالعتبة"
                    if answerable
                    else PROBLEMS[case["problem"]]
                ),
                "caveats": BALANCE_CAVEATS,
            },
            context=cards,
            key={"field": f.key, "from": str(case["d0"]), "day": str(D)},
            field_refs=refs,
            answer_value=cls,
        )
        if it:
            it["related_group"] = related_water(f, D)
            yield it


def refill_rule(ctx) -> str:
    w = wr(ctx)
    lo, hi = w["refill_days"]
    return "\n".join(
        [
            "قاعدة التعويض: نحسب الحجم الإجمالي لتعويض العجز كله، لا الجزء الزائد على الماء الميسّر فقط.",
            "V_gross = Dr × Area / (1000 × Ea)",
            "- الحجم بالمتر المكعب، والعجز بالمليمتر، والمساحة بالمتر المربع.",
            f"- نافذة التدفق: من قراءة نهاية اليوم الذي يسبق اليوم المسؤول عنه بـ{w['flow_window_days']} أيام إلى قراءة نهاية "
            "اليوم المسؤول عنه، والتاريخان مذكوران في السؤال.",
            "Q_well = ΔV / Δhours",
            "Q_total = sum(Q_well)",
            "- غياب طرف من العدادين أو نزوله أو عدم تقدم الساعات يجعل التدفق غير معروف؛ لا تُسقط البئر.",
            "- سجل الحالة well_status_X: القيمة 1 في الخدمة و0 خارج الخدمة، ويسري من تاريخه حتى السجل التالي. البئر الذي "
            f"يقول سجلها 0 في كل أيام الضخ من النافذة تدفقها صفر معروف، دون الحاجة إلى عداد ساعاتها. {PUMP_DAYS_TEXT}.",
            f"- {STALL_TEXT}. وتقدم عداد الماء مع ثبات الساعات يجعل التدفق غير معروف.",
            f"- تعمل الآبار معًا؛ كل يوم تشغيل يساوي {w['max_pump_hours_per_day']:g} ساعات (افتراض سهول).",
            "pump_days = V_gross / (Q_total × hours_per_day)",
            f"- الفئات: {lo:g} أيام أو أقل؛ أكثر من {lo:g} وحتى {hi:g}؛ أكثر من {hi:g}.",
            "- إذا كانت كل آبار الحقل خارج الخدمة بسجل حالة في كل أيام الضخ من النافذة فالتدفق الإجمالي صفر معروف، ولا توجد مدة تعويض "
            "محدودة. التدفق الصفري لا يُستنتج من العدادات وحدها.",
            "- هذا مكافئ ضخ لعجز ثابت، يهمل المطر واستهلاك المحصول أثناء التعويض ولا يتنبأ بزمن التعافي الفعلي.",
        ]
    )


def gen_refill_feasibility(ctx: GenContext):
    """A broken case must not discard valid questions from other fields."""
    for case in stress_cases(ctx):
        try:
            yield from _gen_refill_cases(ctx, [case])
        except Exception as exc:
            ctx.cache.setdefault("case_errors", []).append(
                {
                    "family": "water.refill_feasibility",
                    "field_key": case["field"].key,
                    "day": str(case["d"]),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            ctx.skip("water.refill_feasibility", "case_error")


def _gen_refill_cases(ctx: GenContext, cases):
    fam = "water.refill_feasibility"
    w = wr(ctx)
    lo, hi = w["refill_days"]
    labels = {k: v.format(lo=lo, hi=hi) for k, v in REFILL.items()}
    for case in cases:
        if case.get("skip"):
            ctx.skip(fam, case["skip"])
            continue
        f, fw, D = case["field"], case["fw"], case["d"]
        if case.get("problem"):
            ctx.skip(
                fam, "deficit_unknown_asked_in_stress_status"
            )  # same root cause as that abstention
            continue
        problem = None
        cls = days = None
        flows = {}
        if case["dr"] < w["min_refill_deficit_mm"]:
            ctx.skip(fam, "deficit_too_small")
            continue
        a = D - w["flow_window_days"] * DAY
        if problem is None:
            pumps = fw.of("pump_hours")
            for sx, ms in fw.of("meter").items():
                dv, p1 = window_delta(ms, a, D)
                if p1:
                    problem = p1
                    break
                ip, _ = instrument_problem(fw, sx, a, D, ctx.rules)
                if ip:
                    problem = ip
                    break
                if out_of_service(fw, sx, a, D):  # documented: zero flow is known, hours not needed
                    flows[ms.indicator_id] = {
                        "volume_m3": dv,
                        "hours": None,
                        "flow_m3_h": 0.0,
                        "status": "out_of_service",
                    }
                    continue
                ps = pumps.get(sx)
                if ps is None:
                    problem = "no_pump_hours"
                    break
                dh, p2 = window_delta(ps, a, D)
                if p2:
                    problem = p2
                    break
                if dh <= 0:
                    problem = "pump_hours_not_increasing"
                    break
                if dv <= 0:  # hours below the stall threshold, volume flat: still not a zero flow
                    problem = "volume_meter_stalled"
                    break
                flows[ms.indicator_id] = {"volume_m3": dv, "hours": dh, "flow_m3_h": dv / dh}
        if problem is None:
            q = sum(x["flow_m3_h"] for x in flows.values())
            vol = case["dr"] * f.geom.area_m2 / 1000 / case["prm"]["ea"]
            if q == 0:
                cls = "unavailable"
            else:
                days = vol / (q * w["max_pump_hours_per_day"])
                if min(abs(days - lo) / lo, abs(days - hi) / hi) < w["refill_margin_rel"]:
                    ctx.skip(fam, "days_near_threshold")
                    continue
                cls = "one" if days <= lo else "few" if days <= hi else "many"
        cards, refs = _balance_cards(ctx, case, extra_kinds=("pump_hours",))
        cards.text(refill_rule(ctx))
        it = make_item(
            ctx,
            family=fam,
            level="scene_reasoning",
            max_options=5,
            question=(
                f"إذا شُغّلت آبار الحقل {quote(f.display)} بتدفقها المقيس بين نهاية يوم {a} ونهاية يوم {D}، "
                f"فما مكافئ أيام الضخ لتعويض عجز المنطقة الجذرية في نهاية ذلك اليوم، المحسوب بالموازنة منذ قراءة "
                f"الرطوبة في {case['d0']}، وفق قاعدة التعويض؟"
            ),
            correct=labels[cls] if cls else None,
            answerable=problem is None,
            allow_abstain=False,
            distractors=[labels[k] for k in REFILL if k != cls]
            + ([] if problem else [ABSTAIN_TEXT]),
            evidence={
                "kind": "derived",
                "records": [field_ref(f)]
                + _meter_refs(fw, case["d0"], D)
                + [
                    s.ref(case["d0"], D)
                    for k in ("soil_moisture", "et0", "rain")
                    for s in fw.of(k).values()
                ]
                + _kc_evidence(case),
                "values": {
                    "balance": _balance_values(case),
                    "flows": flows,
                    "pump_days": r2(days),
                    "class": cls,
                    "problem": problem,
                },
                "rule": refill_rule(ctx),
                "computation": (
                    "Dr من الموازنة ← الحجم الإجمالي ← تدفق الآبار من العدادين ← أيام التشغيل"
                    if problem is None
                    else PROBLEMS[problem]
                ),
                "caveats": BALANCE_CAVEATS[:2]
                + [
                    "يفترض تدفقاً ثابتاً كما قيس، ولا يراعي حدود سرعة المحور "
                    "أو معدل الإضافة الأقصى للتربة",
                    "مكافئ حجم ثابت؛ لا يشمل المطر أو ET أثناء التعويض ولا يتنبأ بزمن التعافي",
                ],
            },
            context=cards,
            key={"field": f.key, "from": str(case["d0"]), "day": str(D)},
            field_refs=refs,
            answer_value=cls,
        )
        if it:
            it["related_group"] = related_water(f, D)
            yield it


FAMILIES = {
    "water.applied_depth": ("scene_understanding", gen_applied_depth),
    "water.plan_vs_measured": ("scene_reasoning", gen_plan_vs_measured),
    "water.rain_total": ("object_understanding", gen_rain_total),
    "water.rain_corroboration": ("scene_reasoning", gen_rain_corroboration),
    "water.stress_status": ("scene_reasoning", gen_stress_status),
    "water.refill_feasibility": ("scene_reasoning", gen_refill_feasibility),
}

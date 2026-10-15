"""Level 2 — فهم الهدف: field shape, pivot radius, crop, soil/water classes,
nutrients. Missing values AND values rejected by quality control yield
abstention items (correct answer = no reliable data)."""
from __future__ import annotations

import math
import statistics

from ..arabic import quote
from ..config import classify, describe_classes
from ..facts import match_any
from ..items import GenContext, bin_options, make_item
from .common import EC_CAVEAT, NA, Cards, field_ref, indicator_ref, sample_ref

LEVEL = "object_understanding"

SHAPES = {
    "circle": "دائري (نمط المحور المركزي)",
    "strip": "شريط مستطيل ضيق (الطول أكثر من 4 أضعاف العرض)",
    "rect": "مستطيل أو قريب من المستطيل",
    "irregular": "مضلع غير منتظم",
}
SHAPE_RULE = ("قاعدة الشكل: دائري إذا كان التراصّ 4πA/P² ≥ 0.95؛ وإلا شريط ضيق إذا ملأ المضلع ≥ 85% من أصغر "
              "مستطيل يحيط به وكان طوله ≥ 4 أضعاف عرضه؛ وإلا مستطيل إذا ملأ ≥ 90% منه؛ وإلا مضلع غير منتظم")
YEMEN_CROPS = ["قمح", "ذرة رفيعة", "شعير", "دخن", "برسيم", "طماطم", "بصل", "بطاطس", "سمسم", "بن", "نخيل", "مانجو", "قات"]


def shape_class(f, rules) -> tuple[str | None, dict]:
    g = f.geom
    c = g.compactness
    rect_area, short, long_ = g.min_area_rect()
    fill = g.area_m2 / rect_area if rect_area else 0.0
    aspect = long_ / short if short else 0.0
    sh = rules["shape"]
    m = {"compactness": round(c, 4), "rect_fill": round(fill, 4), "aspect": round(aspect, 2)}
    near = lambda x, t: abs(x - t) < 0.02  # noqa: E731
    if near(c, sh["circle_compactness"]):
        return None, m
    if c >= sh["circle_compactness"]:
        return "circle", m
    if fill >= sh["strip_fill"] and aspect >= sh["strip_aspect"]:
        if near(fill, sh["strip_fill"]) or abs(aspect - sh["strip_aspect"]) < 0.2:
            return None, m
        return "strip", m
    if near(fill, sh["rect_fill"]):
        return None, m
    return ("rect" if fill >= sh["rect_fill"] else "irregular"), m


def gen_shape(ctx: GenContext):
    fam = "field.shape"
    for f in ctx.store.drawn_fields():
        cls, m = shape_class(f, ctx.rules)
        if cls is None:
            ctx.skip(fam, "shape_metric_near_threshold")
            continue
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"ما الوصف الأدق لشكل حدود الحقل {quote(f.display)} كما هي مرسومة في المنصة؟",
            correct=SHAPES[cls], distractors=[t for k, t in SHAPES.items() if k != cls],
            evidence={"kind": "derived", "records": [field_ref(f)], "values": m,
                      "computation": ("تراصّ Polsby–Popper = 4πA/P²؛ نسبة الملء = المساحة ÷ مساحة أصغر مستطيل محيط؛ "
                                      "دائري إذا التراصّ ≥ 0.95، شريط إذا الملء ≥ 0.85 والاستطالة ≥ 4، مستطيل إذا الملء ≥ 0.90")},
            context=Cards().field(f, True).text(SHAPE_RULE), key={"field": f.key}, allow_abstain=False, answer_value=cls)
        if it:
            yield it


def gen_pivot_radius(ctx: GenContext):
    fam = "field.pivot_radius"
    for f in ctx.store.drawn_fields():
        cls, m = shape_class(f, ctx.rules)
        if cls != "circle":
            continue
        r = math.sqrt(f.geom.area_m2 / math.pi)
        correct, dists, meta = bin_options(r, 0.06, "م", ctx.rng(f"{fam}:{f.key}"), min_width=25)
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"حدود الحقل {quote(f.display)} دائرية. ما نصف القطر المكافئ لمساحتها (الطول التقريبي لذراع المحور)؟",
            correct=correct, distractors=dists,
            evidence={"kind": "derived", "records": [field_ref(f)], "values": {"radius_m": round(r, 1), "area_m2": round(f.geom.area_m2, 1), **m, **meta},
                      "computation": "r = √(A/π) من المساحة الإهليلجية التقريبية للمضلع"},
            context=Cards().field(f, True), key={"field": f.key}, answer_value=round(r, 1))
        if it:
            yield it


def gen_crop(ctx: GenContext):
    fam = "field.crop"
    known = sorted({f.crop for f in ctx.store.fields.values() if f.crop})
    for f in ctx.store.fields.values():
        rng = ctx.rng(f"{fam}:{f.key}")
        pool = [c for c in dict.fromkeys(known + YEMEN_CROPS) if c != f.crop]
        rng.shuffle(pool)
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"ما المحصول المسجّل حالياً للحقل {quote(f.display)} في المنصة؟",
            correct=f.crop, distractors=pool[:3], answerable=bool(f.crop),
            evidence={"kind": "observed", "records": [field_ref(f)], "values": {"crop": f.crop},
                      "computation": "قراءة مباشرة لعمود crop" + ("" if f.crop else " — القيمة فارغة، فالإجابة الصحيحة هي الامتناع")},
            context=Cards().field(f), key={"field": f.key, "crop": f.crop}, answer_value=f.crop)
        if it:
            yield it


def _missing_reason(rec, attr: str) -> str:
    if attr in rec.qc:
        q = rec.qc[attr]
        return f"القيمة الخام {q['raw']} مرفوضة بفحص الجودة ({q['code']})، فالإجابة الصحيحة هي الامتناع"
    return f"قيمة {attr} غير مسجّلة (NULL وليست صفراً)، فالإجابة الصحيحة هي الامتناع"


def _class_family(ctx, fam, attr, label_ar, unit, classes_key, *, upper_inclusive=False, caveats=None):
    classes = ctx.rules[classes_key]
    labels = [c["label"] for c in classes]
    rule = describe_classes(classes, unit, upper_inclusive)
    for s in ctx.store.soil:
        val = getattr(s, attr)
        has_any = any(getattr(s, a) is not None for a in ("ph", "ec", "n", "p", "k", "om")) or s.qc
        if val is None and not has_any:
            continue
        answerable = val is not None
        correct = classify(val, classes, upper_inclusive) if answerable else None
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"ما تصنيف {label_ar} للعينة {quote(s.label)} وفق قواعد سهول؟",
            correct=correct, distractors=[x for x in labels if x != correct][:3],
            answerable=answerable,
            evidence={"kind": "derived", "records": [sample_ref(s)], "values": {attr: val, "qc": s.qc.get(attr)}, "rule": rule,
                      "computation": "تطبيق جدول العتبات على القيمة المخبرية المسجّلة" if answerable else _missing_reason(s, attr),
                      "caveats": caveats or []},
            context=Cards().samples([s]).text(f"قاعدة التصنيف: {rule}"),
            key={"sample": s.key, "attr": attr}, answer_value=val)
        if it:
            yield it


def gen_salinity_class(ctx: GenContext):
    yield from _class_family(ctx, "soil.salinity_class", "ec", "ملوحة التربة", "dS/m", "soil_salinity_classes",
                             caveats=[EC_CAVEAT])


def gen_ph_class(ctx: GenContext):
    yield from _class_family(ctx, "soil.ph_class", "ph", "تفاعل التربة (pH)", "", "soil_ph_classes")


NUTRIENTS = {"n": ("النيتروجين", 10.0), "p": ("الفوسفور", 0.25), "k": ("البوتاسيوم", 10.0)}


def gen_nutrient(ctx: GenContext):
    fam = "soil.nutrient"
    typical = {}
    for a in NUTRIENTS:
        vals = sorted(getattr(s, a) for s in ctx.store.soil if getattr(s, a) is not None)
        typical[a] = statistics.median(vals) if vals else {"n": 300.0, "p": 2.5, "k": 300.0}[a]
    for s in ctx.store.soil:
        rng = ctx.rng(f"{fam}:{s.key}")
        missing = [a for a in NUTRIENTS if getattr(s, a) is None]
        present = [a for a in NUTRIENTS if getattr(s, a) is not None]
        has_other = present or s.ec is not None or s.ph is not None or s.qc
        targets = present + ([rng.choice(missing)] if missing and has_other else [])
        for a in targets:
            name, min_w = NUTRIENTS[a]
            val = getattr(s, a)
            base = val if val is not None else typical[a]
            correct, dists, meta = bin_options(base, 0.2, "mg/kg", ctx.rng(f"{fam}:{s.key}:{a}"), min_width=min_w)
            answerable = val is not None
            it = make_item(
                ctx, family=fam, level=LEVEL,
                question=f"ما تركيز {name} في عينة التربة {quote(s.label)} (mg/kg)؟",
                correct=correct if answerable else None,
                distractors=dists if answerable else [correct] + dists[:2],
                answerable=answerable,
                evidence={"kind": "observed", "records": [sample_ref(s)], "values": {a: val, "qc": s.qc.get(a), **(meta if answerable else {})},
                          "computation": "قراءة مباشرة مع تحويلها إلى فئة" if answerable else _missing_reason(s, a)},
                context=Cards().samples([s]), key={"sample": s.key, "nutrient": a}, answer_value=val)
            if it:
                yield it


def gen_water_class(ctx: GenContext):
    fam = "water.salinity_class"
    classes = ctx.rules["water_salinity_classes"]
    pats = ctx.rules["indicator_patterns"]["water_ec"]
    rule = describe_classes(classes, "dS/m")
    for ind in ctx.store.indicators:
        if not match_any(ind.indicator_id, pats):
            continue
        ec = ind.ec_dsm()
        qc = ind.qc.get("value")
        answerable = ec is not None and qc is None
        caveats = []
        if answerable and ind.ec_is_approximate:
            edges = [c[k] for c in classes for k in ("low", "high") if c[k] is not None]
            if min(abs(ec - e) / e for e in edges) < 0.10:
                ctx.skip(fam, "approx_tds_conversion_near_boundary")
                continue
            caveats.append("القيمة TDS بوحدة ppm حُوّلت تقريبياً: EC ≈ TDS ÷ 640 (FAO 29 Rev.1)؛ "
                           "لا يُولَّد السؤال إذا كانت النتيجة ضمن 10% من حدّ فئة")
        correct = classify(ec, classes) if answerable else None
        if answerable:
            why = "تحويل القيمة إلى dS/m ثم تطبيق عتبات USSL"
        elif qc and qc["code"] == "unknown_ec_unit":
            why = f"وحدة القياس {ind.unit!r} غير معروفة فلا يمكن تحويلها إلى dS/m، فالإجابة الصحيحة هي الامتناع"
        else:
            why = _missing_reason(ind, "value")
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"ما فئة خطر الملوحة لمياه الري في المؤشر {quote(ind.indicator_id)} حسب تصنيف مختبر الملوحة الأمريكي (USSL)؟",
            correct=correct, distractors=[c["label"] for c in classes if c["label"] != correct][:3],
            answerable=answerable,
            evidence={"kind": "derived", "records": [indicator_ref(ind)], "values": {"ec_dsm": ec, "raw_value": ind.value, "unit": ind.unit or NA,
                                                                  "qc": qc}, "rule": rule, "computation": why,
                      "caveats": caveats},
            context=Cards().indicators([ind]).text(f"قاعدة التصنيف: {rule}؛ تحويل الوحدات: µS/cm ÷ 1000؛ "
                                                   "mS/cm = dS/m؛ TDS بوحدة ppm أو mg/L ≈ 640 × EC (تقريبي)"),
            key={"ind": ind.key}, answer_value=ec if answerable else None)
        if it:
            yield it


FAMILIES = {
    "field.shape": (LEVEL, gen_shape),
    "field.pivot_radius": (LEVEL, gen_pivot_radius),
    "field.crop": (LEVEL, gen_crop),
    "soil.salinity_class": (LEVEL, gen_salinity_class),
    "soil.ph_class": (LEVEL, gen_ph_class),
    "soil.nutrient": (LEVEL, gen_nutrient),
    "water.salinity_class": (LEVEL, gen_water_class),
}

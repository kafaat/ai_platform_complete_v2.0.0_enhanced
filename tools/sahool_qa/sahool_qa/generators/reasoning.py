"""Level 4 — الاستدلال: rule chains and comparisons whose answers are still
fully determined by stored data (no model-written answers).

Naming is deliberately modest (review, FAO 29 Rev.1 §2.4): an EC threshold
table yields an "EC rule class", not crop suitability; the highest mean EC
flags where to look first, it is not a leaching decision (that needs the
crop, irrigation-water salinity and drainage)."""
from __future__ import annotations

import statistics
from collections import defaultdict

from ..arabic import quote
from ..config import ABSTAIN_TEXT, classify, describe_classes
from ..facts import tenant_key
from ..items import GenContext, make_item
from .common import EC_CAVEAT, Cards, by_year, field_ref, method_note, methods, sample_ref
from .field import _missing_reason, shape_class
from .scene import image_legend, image_ref, raster_stats

LEVEL = "scene_reasoning"
NOT_SUITABILITY = "فئة جدولية من EC وحده؛ لا تقيّم ملاءمة محصول بعينه ولا تراعي ملوحة ماء الري أو الصرف"


def gen_ec_rule_class(ctx: GenContext):
    fam = "reasoning.ec_rule_class"
    classes = ctx.rules["soil_suitability_classes"]
    upper = ctx.rules["soil_suitability_upper_inclusive"]
    rule = describe_classes(classes, "dS/m", upper)
    labels = [c["label"] for c in classes]
    for s in ctx.store.soil:
        if s.ec is None and "ec" not in s.qc:
            continue
        answerable = s.ec is not None
        correct = classify(s.ec, classes, upper) if answerable else None
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=(f"بتطبيق قاعدة EC الجدولية في سهول على قراءة الملوحة للعينة {quote(s.label)}، "
                      "ما الفئة التي تقع فيها؟"),
            correct=correct, distractors=[x for x in labels if x != correct][:3], answerable=answerable,
            evidence={"kind": "derived", "records": [sample_ref(s)], "values": {"ec": s.ec, "qc": s.qc.get("ec")}, "rule": rule,
                      "computation": "سلسلة: قراءة EC ← فحص الجودة ← مقارنتها بعتبات القاعدة" if answerable
                      else _missing_reason(s, "ec"),
                      "caveats": [NOT_SUITABILITY, EC_CAVEAT]},
            context=Cards().samples([s]).text(f"قاعدة EC الجدولية: {rule}"),
            key={"sample": s.key}, answer_value=correct)
        if it:
            yield it


def gen_highest_mean_ec(ctx: GenContext):
    """Which drawn field has the highest mean EC in its most recent sampled year."""
    fam = "reasoning.highest_mean_ec"
    margin = ctx.rules["comparison_margin_rel"]
    groups = defaultdict(list)
    for f in ctx.store.drawn_fields():
        pairs = ctx.store.samples_for(f)
        yrs = {y: [s for s in ss if s.ec is not None] for y, ss in by_year(pairs).items()}
        yrs = {y: ss for y, ss in yrs.items() if len(ss) >= ctx.rules["min_samples_aggregate"]}
        if not yrs:
            continue
        y = max(yrs)
        groups[(tenant_key(f.tenant), f.governorate)].append((f, y, yrs[y], statistics.fmean(s.ec for s in yrs[y]), methods(pairs)))
    for (tenant, gov), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: (-r[3], r[0].key))
        if rows[0][3] - rows[1][3] < margin * rows[0][3]:
            ctx.skip(fam, "no_clear_leader")
            continue
        names = [r[0].display for r in rows]
        if len(set(names)) != len(names):
            ctx.skip(fam, "duplicate_field_names")
            continue
        rng = ctx.rng(f"{fam}:{tenant}:{gov}")
        others = rows[1:]
        rng.shuffle(others)
        all_s = [s for r in rows for s in r[2]]
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=(f"بالنظر إلى أحدث سنة توفرت فيها عيّنات لكل حقل مرسوم له عيّنات في محافظة {gov or 'غير محددة'}، "
                      "أيّ الحقول التالية سجّل أعلى متوسط ملوحة تربة (EC)؟"),
            # with only two fields, "no reliable data" is offered as the third option
            correct=rows[0][0].display,
            distractors=[r[0].display for r in others[:3]] + ([ABSTAIN_TEXT] if len(others) < 2 else []),
            evidence={"kind": "derived", "records": [field_ref(r[0]) for r in rows] + [sample_ref(s) for s in all_s],
                      "values": {r[0].display: {"year": r[1], "mean_ec": round(r[3], 4), "n": len(r[2])} for r in rows},
                      "computation": "لكل حقل: أحدث سنة فيها عينتان صالحتان على الأقل ← متوسط EC ← الأعلى بفارق ≥ "
                                     f"{int(margin * 100)}% عن الثاني؛ " + method_note(sorted({m for r in rows for m in r[4]})),
                      "caveats": ["مؤشر لأولوية الفحص الميداني، لا قرار غسيل: يلزم المحصول وملوحة ماء الري والصرف", EC_CAVEAT]},
            context=Cards().fields([r[0] for r in rows], True).samples(all_s),
            key={"scope": sorted(r[0].key for r in rows)}, answer_value=rows[0][0].key)
        if it:
            yield it


QUADRANTS = {"NE": "الربع الشمالي الشرقي", "SE": "الربع الجنوبي الشرقي",
             "SW": "الربع الجنوبي الغربي", "NW": "الربع الشمالي الغربي"}


def gen_pivot_weak_quadrant(ctx: GenContext):
    fam = "reasoning.pivot_weak_quadrant"
    for f, layer, thr, st, ok in raster_stats(ctx):
        if not ok:
            continue
        cls, _ = shape_class(f, ctx.rules)
        if cls != "circle":
            continue
        q = st["quadrants"]
        if any(v["valid"] < 20 or v["frac_above"] is None for v in q.values()):
            ctx.skip(fam, "quadrant_too_small")
            continue
        ranked = sorted(q.items(), key=lambda kv: (kv[1]["frac_above"], kv[0]))
        if ranked[1][1]["frac_above"] - ranked[0][1]["frac_above"] < 0.10:
            ctx.skip(fam, "no_clear_weak_quadrant")
            continue
        weak = ranked[0][0]
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=(f"في طبقة {layer.index_name} بتاريخ {layer.date}، أيّ أرباع المحور {quote(f.display)} "
                      f"سجّل أدنى نسبة غطاء نباتي ({layer.index_name} ≥ {thr})؟"),
            correct=QUADRANTS[weak], distractors=[t for k, t in QUADRANTS.items() if k != weak],
            evidence={"kind": "derived", "records": [field_ref(f)], "values": {k: round(v["frac_above"], 4) for k, v in q.items()},
                      "computation": "تقسيم المضلع إلى أرباع حول مركزه ← نسبة البكسلات ≥ العتبة في كل ربع ← الأدنى بفارق ≥ 10 نقاط",
                      "synthetic_raster": layer.synthetic},
            context=Cards().field(f, True).text(image_legend(layer, thr, f)),
            key={"field": f.key, "raster": layer.key}, answer_value=weak)
        if it:
            it["image_ref"] = image_ref(layer, f, thr)
            yield it


FAMILIES = {
    "reasoning.ec_rule_class": (LEVEL, gen_ec_rule_class),
    "reasoning.highest_mean_ec": (LEVEL, gen_highest_mean_ec),
    "reasoning.pivot_weak_quadrant": (LEVEL, gen_pivot_weak_quadrant),
}

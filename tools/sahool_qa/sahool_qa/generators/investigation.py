"""Season investigator — first building blocks ("open a past season, find where
and when it diverged, show the evidence").

  reasoning.pivot_anomaly_pattern  ring vs sector vs field-wide vs none (image)
  reasoning.next_measurement       which measurement best separates the hypotheses
  temporal.divergence_onset        when a sector first diverged, honouring scene
                                   validity and persistence (one-off dips ignored)
  temporal.green_up_window         interval in which canopy first crossed the threshold

On a centre pivot the geometry of the weak area separates hypotheses before any
new data is requested: a ring points at the sprinkler package along the arm,
a sector at something that varied with angle or time of passage (speed,
stops, end gun, pressure with elevation, wind), a field-wide weakness at
total water, weather or crop stage. Answers stay rule-computed; the
recommendation family is labelled "inferred" because it still needs a
field check.
"""

from __future__ import annotations

from ..arabic import quote
from ..geo import DIRECTIONS_AR
from ..items import GenContext, make_item
from ..raster import SECTOR_KEYS, polar_stats
from .common import Cards, field_ref, indicator_ref
from .field import shape_class
from .scene import DAILY_NOTE, _index_series, _segments, image_legend, image_ref

PATTERNS = {
    "ring": "حلقة: ضعف في نطاق على بُعد معيّن من مركز المحور يمتد حول الدائرة كلها",
    "sector": "قطاع: ضعف في إسفين يمتد من المركز إلى الطرف في اتجاه معيّن",
    "field_wide": "ضعف عام متقارب في كامل المحور",
    "none": "لا يظهر ضعف مكاني واضح",
}
MEASUREMENTS = {
    "ring": "قياس توزيع الماء بأوعية جمع على امتداد الذراع، وفحص الفوهات ومنظّمات الضغط في النطاق الضعيف",
    "sector": "مراجعة سجل موضع المحور وسرعته وتوقفاته وضغط التشغيل عند تلك الزاوية، ومقارنتها بالارتفاع واتجاه الريح",
    "field_wide": "مراجعة كمية الري الكلية وإنتاجية الآبار والطقس ومرحلة النمو للحقل كله",
    "none": "لا يلزم قياس تمييزي الآن؛ متابعة المشهد الصالح التالي",
    "insufficient_valid": "الحصول على مشهد صالح أو صورة بديلة أولاً؛ المشهد الحالي لا يحدد النمط",
}
SECTOR_AR = dict(zip(SECTOR_KEYS, DIRECTIONS_AR, strict=False))


SECTOR_TOWARD = {
    "N": "الشمال",
    "NE": "الشمال الشرقي",
    "E": "الشرق",
    "SE": "الجنوب الشرقي",
    "S": "الجنوب",
    "SW": "الجنوب الغربي",
    "W": "الغرب",
    "NW": "الشمال الغربي",
}


def sector_phrase(k: str) -> str:
    return f"القطاع المتجه نحو {SECTOR_TOWARD[k]} من مركز المحور"


def r4(x):
    return None if x is None else round(x, 4)


def pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


# ───────────────────────── classification ─────────────────────────


def classify_pattern(polar: dict, rules: dict) -> tuple[str | None, dict]:
    """(class, detail) or (None, {"reason": ...}) when the case is ambiguous."""
    pr = rules["pattern"]
    A, tol, m = pr["anomaly_deficit"], pr["uniform_tol"], pr["margin"]
    fld = polar["field"]
    if fld["valid_frac"] < pr["min_valid_frac"] or fld["frac_above"] is None:
        return None, {"reason": "too_little_valid_data"}
    bins = polar["rings"] + list(polar["sectors"].values())
    if any(b["valid"] < pr["min_bin_pixels"] or b["frac_above"] is None for b in bins):
        return None, {"reason": "too_few_pixels_in_a_bin"}
    F = fld["frac_above"]
    rings = [r["frac_above"] for r in polar["rings"]]
    sectors = {k: v["frac_above"] for k, v in polar["sectors"].items()}
    ring_spread, sector_spread = (
        max(rings) - min(rings),
        max(sectors.values()) - min(sectors.values()),
    )
    ring_def, sector_def = F - min(rings), F - min(sectors.values())
    detail = {
        "field_share": round(F, 4),
        "ring_spread": round(ring_spread, 4),
        "sector_spread": round(sector_spread, 4),
        "ring_deficit": round(ring_def, 4),
        "sector_deficit": round(sector_def, 4),
    }
    # only the thresholds that decide this case must be clear of the margin
    near = [abs(ring_spread - tol), abs(sector_spread - tol)]
    if ring_spread < tol and sector_spread < tol:
        near += [abs(F - pr["healthy_min"]), abs(F - pr["fieldwide_max"])]
    else:
        near += [abs(ring_def - A), abs(sector_def - A)]
    if min(near) < m:
        return None, {**detail, "reason": "metric_near_threshold"}
    if ring_spread < tol and sector_spread < tol:
        if F > pr["healthy_min"]:
            return "none", detail
        if F < pr["fieldwide_max"]:
            return "field_wide", detail
        return None, {**detail, "reason": "uniform_but_intermediate"}
    if ring_def > A and sector_spread < tol:
        k = rings.index(min(rings))
        return "ring", {
            **detail,
            "weak_ring": k,
            "weak_ring_m": [polar["rings"][k]["r_from"], polar["rings"][k]["r_to"]],
        }
    if sector_def > A and ring_spread < tol:
        k = min(sectors, key=lambda s: (sectors[s], s))
        return "sector", {**detail, "weak_sector": k}
    return None, {**detail, "reason": "mixed_pattern"}


def pattern_rule_text(rules: dict) -> str:
    pr = rules["pattern"]
    A, tol = int(100 * pr["anomaly_deficit"]), int(100 * pr["uniform_tol"])
    return (
        f"قاعدة النمط — أولاً، قبل أي بند آخر: إذا كان أقل من {int(100 * pr['min_valid_frac'])}% من بكسلات المحور صالحاً "
        "(الرمادي = سحب أو بلا بيانات) فالنمط غير قابل للتحديد من هذا المشهد. وإلا (النسب = حصة البكسلات الصالحة التي "
        f"بلغت العتبة): حلقة إذا قلّت حلقة واحدة عن الحقل بأكثر من {A} نقطة وكان الفرق بين أعلى قطاع وأدناه أقل من {tol} "
        f"نقطة؛ قطاع إذا قلّ قطاع عن الحقل بأكثر من {A} نقطة وكان الفرق بين أعلى حلقة وأدناها أقل من {tol} نقطة؛ إذا "
        f"تقاربت الحلقات والقطاعات (أقل من {tol} نقطة) فالضعف عام إن كانت حصة الحقل أقل من "
        f"{int(100 * pr['fieldwide_max'])}%، ولا ضعف واضح إن زادت على {int(100 * pr['healthy_min'])}%"
    )


def measurement_rule_text() -> str:
    return "قاعدة القياس التالي في سهول: " + "؛ ".join(
        f"{lab} ← {MEASUREMENTS[k]}"
        for k, lab in (
            ("ring", "حلقة"),
            ("sector", "قطاع"),
            ("field_wide", "ضعف عام"),
            ("none", "لا ضعف واضح"),
            ("insufficient_valid", "نمط غير قابل للتحديد"),
        )
    )


def pattern_rows(ctx: GenContext):
    """Cached (field, layer, threshold, polar, class, detail) for circular fields on scene layers."""
    cache = ctx.cache.setdefault("pattern", {})
    if "rows" in cache:
        return cache["rows"]
    rows = []
    circles = [f for f in ctx.store.drawn_fields() if shape_class(f, ctx.rules)[0] == "circle"]
    for layer in ctx.store.rasters:
        thr = ctx.rules["vegetation_threshold"].get(layer.index_name)
        if layer.role != "all" or thr is None:
            continue
        for f in circles:
            polar = polar_stats(layer, f.geom, thr, ctx.rules["pattern"]["n_rings"])
            if polar is None:
                continue
            cls, detail = classify_pattern(polar, ctx.rules)
            rows.append((f, layer, thr, polar, cls, detail))
    cache["rows"] = rows
    return rows


def polar_table(polar: dict) -> str:
    rings = "؛ ".join(
        f"{r['r_from']:.0f}-{r['r_to']:.0f} م: {pct(r['frac_above'])}" for r in polar["rings"]
    )
    sectors = "؛ ".join(
        f"{SECTOR_AR[k]}: {pct(v['frac_above'])}" for k, v in polar["sectors"].items()
    )
    return (
        f"جدول التغطية المحسوب من الطبقة — الحقل كله: {pct(polar['field']['frac_above'])} "
        f"(الصالح {pct(polar['field']['valid_frac'])})\nالحلقات من المركز: {rings}\nالقطاعات: {sectors}"
    )


# ───────────────────────── families ─────────────────────────


def gen_pivot_anomaly_pattern(ctx: GenContext):
    fam = "reasoning.pivot_anomaly_pattern"
    for f, layer, thr, polar, cls, detail in pattern_rows(ctx):
        cloudy = cls is None and detail["reason"] == "too_little_valid_data"
        if cls is None and not cloudy:
            ctx.skip(fam, detail["reason"])
            continue
        cls = "insufficient_valid" if cloudy else cls
        it = make_item(
            ctx,
            family=fam,
            level="scene_reasoning",
            question=(
                f"في طبقة {layer.index_name} بتاريخ {layer.date}، ما النمط الأدق لتوزيع الضعف داخل المحور "
                f"{quote(f.display)}؟ (الضعف = {layer.index_name} أقل من {thr})"
            ),
            correct=None if cloudy else PATTERNS[cls],
            answerable=not cloudy,
            # for a half-clouded pivot the visible half often looks healthy: keep "none" among the options
            distractors=([PATTERNS["none"]] if cloudy else [])
            + [t for k, t in PATTERNS.items() if k not in (cls, "none")]
            + ([] if cloudy else [PATTERNS["none"]]),
            evidence={
                "kind": "derived",
                "records": [field_ref(f)],
                "values": {
                    "class": cls,
                    **detail,
                    "field_valid_frac": r4(polar["field"]["valid_frac"]),
                    "rings": [r4(r["frac_above"]) for r in polar["rings"]],
                    "sectors": {k: r4(v["frac_above"]) for k, v in polar["sectors"].items()},
                },
                "rule": pattern_rule_text(ctx.rules),
                "computation": "تقسيم المحور إلى 5 حلقات متساوية العرض و8 قطاعات بعرض 45° حول مركزه، ثم مقارنة حصة "
                "البكسلات البالغة العتبة في كل منها بحصة الحقل",
                "synthetic_raster": layer.synthetic,
            },
            context=Cards()
            .field(f, True)
            .text(image_legend(layer, thr, f))
            .text(pattern_rule_text(ctx.rules)),
            key={"field": f.key, "raster": layer.key},
            answer_value=cls,
        )
        if it:
            it["image_ref"] = image_ref(layer, f, thr)
            it["related_group"] = related_group(f, layer)
            yield it


def gen_next_measurement(ctx: GenContext):
    fam = "reasoning.next_measurement"
    for f, layer, _thr, polar, cls, detail in pattern_rows(ctx):
        if cls is None and detail["reason"] == "too_little_valid_data":
            cls = "insufficient_valid"
        elif cls is None:
            ctx.skip(fam, detail["reason"])
            continue
        it = make_item(
            ctx,
            family=fam,
            level="scene_reasoning",
            question=(
                f"بحسب جدول تغطية {layer.index_name} للمحور {quote(f.display)} في مشهد {layer.date} وقاعدتي النمط "
                "والقياس في سهول، ما القياس التالي الأقدر على التمييز بين الفرضيات؟"
            ),
            correct=MEASUREMENTS[cls],
            distractors=([MEASUREMENTS["none"]] if cls == "insufficient_valid" else [])
            + sorted(
                (t for k, t in MEASUREMENTS.items() if k not in (cls, "none")),
                key=lambda t: ctx.rng(f"{fam}:{f.key}:{layer.key}:{t}").random(),
            )
            + ([] if cls == "insufficient_valid" else [MEASUREMENTS["none"]]),
            evidence={
                "kind": "inferred",
                "records": [field_ref(f)],
                "values": {"class": cls, **detail},
                "rule": pattern_rule_text(ctx.rules) + " — " + measurement_rule_text(),
                "computation": "تصنيف النمط من الجدول ← اختيار القياس الذي يميّز فرضيات ذلك النمط",
                "caveats": [
                    "القياس المقترح يميّز بين الفرضيات ولا يثبت السبب؛ الحكم النهائي بعد الفحص الميداني"
                ],
                "synthetic_raster": layer.synthetic,
            },
            context=Cards()
            .field(f, True)
            .text(polar_table(polar))
            .text(pattern_rule_text(ctx.rules))
            .text(measurement_rule_text()),
            key={"field": f.key, "raster": layer.key},
            answer_value=cls,
        )
        if it:
            it["related_group"] = related_group(f, layer)
            yield it


def related_group(f, layer) -> str:
    """Items built from the same field and scene. The table in next_measurement reveals the
    pattern asked in the image item, so never show both in one prompt or few-shot context."""
    import hashlib

    return "rg-" + hashlib.sha1(f"{f.key}|{layer.key}".encode()).hexdigest()[:10]


NO_DIVERGENCE = "لم يظهر انحراف موثوق في هذا القطاع خلال الفترة"


def _window(a, b) -> str:
    return f"بين مشهد {a} ومشهد {b}"


def onset_rule_text(rules: dict) -> str:
    dv = rules["divergence"]
    return (
        f"قاعدة الانحراف الموثوق: يُعتدّ بالمشهد فقط إذا كان {int(100 * dv['min_field_valid'])}% على الأقل من بكسلات الحقل "
        f"و{int(100 * dv['min_sector_valid'])}% من بكسلات القطاع صالحة؛ والانحراف موثوق إذا قلّت تغطية القطاع عن بقية الحقل "
        f"بـ {int(100 * dv['deficit'])} نقطة أو أكثر في مشهدين صالحين متتاليين (الانخفاض في مشهد صالح واحد لا يُعدّ). "
        "بداية الانحراف تقع بين المشهد الصالح السابق لأول زوج منحرف وأول مشاهد ذلك الزوج؛ وإذا بدأ أول زوج منحرف عند "
        "أول مشهد صالح في السلسلة فالبداية سبقت البيانات المتاحة ولا يمكن تحديدها منها"
    )


def gen_divergence_onset(ctx: GenContext):
    fam = "temporal.divergence_onset"
    dv = ctx.rules["divergence"]
    D, mg = dv["deficit"], dv["margin"]
    circles = [f for f in ctx.store.drawn_fields() if shape_class(f, ctx.rules)[0] == "circle"]
    for f in circles:
        by_index = {}
        for layer in ctx.store.rasters:
            thr = ctx.rules["vegetation_threshold"].get(layer.index_name)
            if thr is None or layer.date is None:
                continue
            polar = polar_stats(layer, f.geom, thr, ctx.rules["pattern"]["n_rings"])
            if polar is not None:
                by_index.setdefault(layer.index_name, []).append((layer.date, layer, thr, polar))
        for name, scenes in sorted(by_index.items()):
            scenes.sort(key=lambda t: (t[0], t[1].key))
            for seg in _segments(scenes, dv["max_gap_days"]):
                if len(seg) < dv["min_scenes"]:
                    ctx.skip(fam, "too_few_scenes")
                    continue

                def scene_row(t, k):
                    _, _, _, p = t
                    sec, rest = p["sectors"][k], p["rest_of_field"][k]
                    ok = (
                        p["field"]["valid_frac"] >= dv["min_field_valid"]
                        and sec["valid_frac"] >= dv["min_sector_valid"]
                        and sec["frac_above"] is not None
                        and rest["frac_above"] is not None
                    )
                    deficit = (rest["frac_above"] - sec["frac_above"]) if ok else None
                    return {
                        "valid": ok,
                        "deficit": deficit,
                        "field_valid": p["field"]["valid_frac"],
                        "sector_valid": sec["valid_frac"],
                        "sector": sec["frac_above"],
                        "rest": rest["frac_above"],
                    }

                best = {
                    k: max(
                        (r["deficit"] for r in (scene_row(t, k) for t in seg) if r["valid"]),
                        default=-1.0,
                    )
                    for k in SECTOR_KEYS
                }
                ranked = sorted(best, key=lambda k: (-best[k], k))
                k = ranked[0]
                if best[k] < D - mg:
                    ctx.skip(fam, "no_sector_dips")
                    continue
                if best[ranked[1]] >= D - mg:
                    ctx.skip(fam, "two_sectors_dip")
                    continue
                rows = [scene_row(t, k) for t in seg]
                if any(r["valid"] and abs(r["deficit"] - D) < mg for r in rows):
                    ctx.skip(fam, "deficit_near_threshold")
                    continue
                valid_idx = [i for i, r in enumerate(rows) if r["valid"]]
                if len(valid_idx) < 3:
                    ctx.skip(fam, "too_few_valid_scenes")
                    continue
                onset = None
                for j in range(len(valid_idx) - dv["persist"] + 1):
                    if all(rows[valid_idx[j + q]]["deficit"] >= D for q in range(dv["persist"])):
                        onset = j
                        break
                dates = [str(t[0]) for t in seg]
                answerable = onset != 0
                if onset is None:
                    correct, val, focus = NO_DIVERGENCE, None, valid_idx[0]
                elif onset == 0:
                    correct, val, focus = None, None, valid_idx[0]
                else:
                    a, b = valid_idx[onset - 1], valid_idx[onset]
                    correct, val, focus = _window(dates[a], dates[b]), [dates[a], dates[b]], b
                # hardest distractors first: windows that end nearest the true onset (e.g. the one that
                # starts at an invalid scene, or the one around a one-off dip)
                order = sorted(range(len(dates) - 1), key=lambda i: (abs(i + 1 - focus), i))
                windows = [_window(dates[i], dates[i + 1]) for i in order]
                distractors = ([NO_DIVERGENCE] if correct != NO_DIVERGENCE else []) + [
                    w for w in windows if w != correct
                ]
                head, tail = distractors[:1], distractors[1:]
                table = "\n".join(
                    f"مشهد {dates[i]}: الصالح من الحقل {pct(r['field_valid'])}، الصالح من القطاع {pct(r['sector_valid'])}، "
                    f"تغطية القطاع {pct(r['sector'])}، بقية الحقل {pct(r['rest'])}"
                    for i, r in enumerate(rows)
                )
                it = make_item(
                    ctx,
                    family=fam,
                    level="scene_understanding",
                    question=(
                        f"في سلسلة مشاهد {name} للمحور {quote(f.display)} من {dates[0]} إلى {dates[-1]}، متى بدأ أول "
                        f"انحراف موثوق في {sector_phrase(k)}؟"
                    ),
                    correct=correct,
                    distractors=head + tail,
                    answerable=answerable,
                    allow_abstain=False,
                    evidence={
                        "kind": "derived",
                        "records": [field_ref(f)],
                        "values": {
                            "sector": k,
                            "onset_window": val,
                            "scenes": [
                                {
                                    "date": dates[i],
                                    "valid": r["valid"],
                                    "deficit": None
                                    if r["deficit"] is None
                                    else round(r["deficit"], 4),
                                }
                                for i, r in enumerate(rows)
                            ],
                            "scene_ids": [t[1].scene_id for t in seg],
                        },
                        "rule": onset_rule_text(ctx.rules),
                        "computation": "لكل مشهد: حصة البكسلات البالغة العتبة في القطاع وفي بقية الحقل؛ استبعاد المشاهد غير "
                        "الصالحة؛ أول مشهدين صالحين متتاليين بفارق ≥ العتبة"
                        + (
                            ""
                            if answerable
                            else "؛ الانحراف قائم منذ أول مشهد صالح، فبدايته غير معروفة"
                        ),
                        "synthetic_raster": any(t[1].synthetic for t in seg),
                    },
                    context=Cards()
                    .field(f, True)
                    .text(onset_rule_text(ctx.rules))
                    .text(
                        f"جدول المحسوب من الطبقات لـ{sector_phrase(k)} (العتبة {name} ≥ {seg[0][2]}):\n{table}"
                    ),
                    key={
                        "field": f.key,
                        "index": name,
                        "from": dates[0],
                        "to": dates[-1],
                        "sector": k,
                    },
                    answer_value=val,
                )
                if it:
                    yield it


def green_rule_text(name, thr) -> str:
    return (
        f"قاعدة تجاوز العتبة: أول قيمة يومية لـ{name} ≥ {thr} تتبعها قيمة أخرى ≥ {thr} مباشرة؛ "
        "التجاوز يقع بين تلك الرصدة والرصدة التي قبلها؛ وإذا كانت أول رصدة في الفترة فوق العتبة فالتجاوز سبق الفترة "
        "والبيانات المتاحة لا تكفي لتحديد نافذته"
    )


def gen_green_up_window(ctx: GenContext):
    fam = "temporal.green_up_window"
    gu = ctx.rules["green_up"]
    for (fk, name), series in _index_series(ctx).items():
        thr = ctx.rules["vegetation_threshold"].get(name)
        if thr is None:
            continue
        f = ctx.store.fields[fk]
        for pts in _segments(series):
            if len(pts) < gu["min_points"]:
                ctx.skip(fam, "season_too_short")
                continue
            vals = [v for _, v, _ in pts]
            dates = [str(d) for d, _, _ in pts]
            k = next(
                (i for i in range(len(vals) - 1) if vals[i] >= thr and vals[i + 1] >= thr), None
            )
            upto = len(vals) if k is None else k + 2
            if any(abs(v - thr) < gu["margin"] for v in vals[:upto]):
                ctx.skip(fam, "value_near_threshold")
                continue
            never = f"لم يتجاوز {name} العتبة {thr} بشكل مستمر خلال الفترة"
            windows = [f"بين رصدة {dates[i]} ورصدة {dates[i + 1]}" for i in range(len(dates) - 1)]
            if k is None:
                correct, val = never, None
            elif k == 0:
                correct, val = None, None
            else:
                correct, val = windows[k - 1], [dates[k - 1], dates[k]]
            near = [] if k is None else [windows[i] for i in (k - 2, k, 0) if 0 <= i < len(windows)]
            pool = [w for w in near + windows if w != correct]
            distractors = ([never] if correct != never else []) + list(dict.fromkeys(pool))
            inds = [i for _, _, day in pts for i in day]
            it = make_item(
                ctx,
                family=fam,
                level="scene_understanding",
                question=(
                    f"خلال الفترة من {dates[0]} إلى {dates[-1]}، متى تجاوز مؤشر {name} في الحقل {quote(f.display)} "
                    f"العتبة {thr} لأول مرة بشكل مستمر؟"
                ),
                correct=correct,
                distractors=distractors,
                answerable=k != 0,
                allow_abstain=False,
                evidence={
                    "kind": "derived",
                    "records": [field_ref(f)] + [indicator_ref(i) for i in inds],
                    "values": {
                        "threshold": thr,
                        "first_sustained_index": k,
                        "window": val,
                        "daily_values": dict(zip(dates, [round(v, 4) for v in vals], strict=False)),
                    },
                    "rule": green_rule_text(name, thr),
                    "computation": f"مسح القيم اليومية بالترتيب حتى أول قيمتين متتاليتين ≥ العتبة؛ {DAILY_NOTE}"
                    + ("" if k != 0 else "؛ أول رصدة فوق العتبة فبداية التجاوز قبل الفترة"),
                    "caveats": [
                        "تجاوز العتبة مؤشر على تكوّن الغطاء النباتي لا على تاريخ الإنبات نفسه؛ "
                        "دقة النافذة محدودة بتباعد الرصدات"
                    ],
                },
                context=Cards().field(f).indicators(inds).text(green_rule_text(name, thr)),
                key={"field": fk, "index": name, "from": dates[0], "to": dates[-1]},
                answer_value=val,
            )
            if it:
                yield it


FAMILIES = {
    "reasoning.pivot_anomaly_pattern": ("scene_reasoning", gen_pivot_anomaly_pattern),
    "reasoning.next_measurement": ("scene_reasoning", gen_next_measurement),
    "temporal.divergence_onset": ("scene_understanding", gen_divergence_onset),
    "temporal.green_up_window": ("scene_understanding", gen_green_up_window),
}

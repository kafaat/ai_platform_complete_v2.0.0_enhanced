"""Level 3 — فهم المشهد: area, area share, sample counts, EC aggregates,
vegetation coverage from rasters, and change over time.

Same-day indicator readings are aggregated explicitly (daily mean), so the
answer never depends on the order rows come back from the database (F12).
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from ..arabic import MONTHS, quote
from ..facts import tenant_key
from ..items import GenContext, bin_options, make_item
from ..raster import polygon_stats
from .common import EC_CAVEAT, Cards, by_year, field_ref, indicator_ref, method_note, methods, sample_ref

LEVEL = "scene_understanding"


def gen_area(ctx: GenContext):
    fam = "scene.area"
    for f in ctx.store.fields.values():
        if f.geom_problems:
            ctx.skip(fam, "invalid_geometry")       # reported by the audit
            continue
        rng = ctx.rng(f"{fam}:{f.key}")
        if f.geom is not None:
            ha = f.geom.area_m2 / 1e4
            if ha <= 0:
                ctx.skip(fam, "invalid_geometry")
                continue
            if f.area_ha_stored and abs(f.area_ha_stored - ha) / ha > 0.05:
                ctx.skip(fam, "stored_area_disagrees_with_polygon")
                continue
            src = "polygon"
        elif f.area_ha_stored:
            ha, src = f.area_ha_stored, "stored"
        else:
            ha, src = None, "none"
        base = ha if ha is not None else 10.0
        correct, dists, meta = bin_options(base, 0.12, "هكتار", rng, min_width=0.5)
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"ما المساحة التقريبية للحقل {quote(f.display)}؟",
            correct=correct if ha is not None else None,
            distractors=dists if ha is not None else [correct] + dists[:2],
            answerable=ha is not None,
            evidence={"kind": "derived" if src == "polygon" else "observed", "records": [field_ref(f)],
                      "values": {"area_ha": None if ha is None else round(ha, 4), "source": src,
                                 "stored_area_ha": f.area_ha_stored, **(meta if ha is not None else {})},
                      "computation": {"polygon": "مساحة إهليلجية تقريبية للمضلع (إطار محلي متساوي المساحة على WGS84؛ "
                                                 "خطأ نسبي مقيس < 1e-4 مقابل الصيغة الدقيقة) ÷ 10,000",
                                      "stored": "قيمة area_ha المسجّلة (لا توجد حدود مرسومة)",
                                      "none": "لا حدود مرسومة ولا مساحة مسجّلة، فالإجابة الصحيحة هي الامتناع"}[src]},
            context=Cards().field(f, True), key={"field": f.key, "src": src}, answer_value=ha)
        if it:
            yield it


def gen_area_share(ctx: GenContext):
    fam = "scene.area_share"
    groups = defaultdict(list)
    for f in ctx.store.drawn_fields():
        groups[(tenant_key(f.tenant), f.governorate)].append(f)
    for (tenant, gov), fs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        if len(fs) < 2:
            continue
        total = sum(f.geom.area_m2 for f in fs)
        for f in fs:
            pct = 100 * f.geom.area_m2 / total
            correct, dists, meta = bin_options(pct, 0, "%", ctx.rng(f"{fam}:{f.key}"), width=10, floor=0, ceil=100)
            it = make_item(
                ctx, family=fam, level=LEVEL,
                question=(f"ما نسبة مساحة الحقل {quote(f.display)} من مجموع مساحات الحقول المرسومة "
                          f"لدى المستأجر نفسه في محافظة {gov or 'غير محددة'}؟"),
                correct=correct, distractors=dists,
                evidence={"kind": "derived", "records": [field_ref(x) for x in fs],
                          "values": {"share_pct": round(pct, 2), "field_area_ha": round(f.geom.area_m2 / 1e4, 3),
                                     "total_area_ha": round(total / 1e4, 3), "n_fields": len(fs), **meta},
                          "computation": "مساحة الحقل ÷ مجموع مساحات الحقول المرسومة الصالحة في النطاق نفسه × 100"},
                context=Cards().fields(fs, True), key={"field": f.key, "scope": sorted(x.key for x in fs)},
                answer_value=round(pct, 2))
            if it:
                yield it


def gen_sample_count(ctx: GenContext):
    fam = "scene.sample_count"
    for f in ctx.store.fields.values():
        pairs = ctx.store.samples_for(f)
        for year, ss in sorted(by_year(pairs).items()):
            n = len(ss)
            rng = ctx.rng(f"{fam}:{f.key}:{year}")
            cands = [x for x in (n - 2, n - 1, n + 1, n + 2, n + 3) if x >= 0]
            rng.shuffle(cands)
            it = make_item(
                ctx, family=fam, level=LEVEL,
                question=f"كم عدد سجلات عينات التربة المرتبطة بالحقل {quote(f.display)} في عام {year}؟",
                correct=str(n), distractors=[str(x) for x in cands[:3]], allow_abstain=False,
                evidence={"kind": "derived", "records": [field_ref(f)] + [sample_ref(s) for s in ss],
                          "values": {"count": n, "association": methods(pairs)},
                          "computation": "عدد السجلات المميّزة (المستأجر، الحقل، العينة، الوقت، المعرّف) للسنة؛ "
                                         + method_note(methods(pairs))},
                # every record shown is a dependency, so other years' records cannot leak across splits
                context=Cards().field(f, True).samples([s for s, _ in pairs]),
                key={"field": f.key, "year": year}, answer_value=n)
            if it:
                yield it


def _ec_by_field_year(ctx):
    out = {}
    for f in ctx.store.fields.values():
        pairs = ctx.store.samples_for(f)
        for year, ss in by_year(pairs).items():
            withec = [s for s in ss if s.ec is not None]     # QC-rejected values are already None
            if len(withec) >= ctx.rules["min_samples_aggregate"]:
                out[(f.key, year)] = (withec, methods(pairs))
    return out


def gen_mean_ec(ctx: GenContext):
    fam = "soil.mean_ec"
    for (fk, year), (ss, ms) in sorted(_ec_by_field_year(ctx).items()):
        f = ctx.store.fields[fk]
        mean = statistics.fmean(s.ec for s in ss)
        correct, dists, meta = bin_options(mean, 0.15, "dS/m", ctx.rng(f"{fam}:{fk}:{year}"), min_width=0.25)
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"ما متوسط ملوحة التربة (EC) لعينات الحقل {quote(f.display)} في عام {year}؟",
            correct=correct, distractors=dists,
            evidence={"kind": "derived", "records": [field_ref(f)] + [sample_ref(s) for s in ss],
                      "values": {"mean_ec": round(mean, 4), "n": len(ss), "values": [s.ec for s in ss], **meta},
                      "computation": "المتوسط الحسابي لقيم EC الصالحة؛ " + method_note(ms), "caveats": [EC_CAVEAT]},
            context=Cards().field(f, True).samples(ss), key={"field": fk, "year": year}, answer_value=round(mean, 4))
        if it:
            yield it


def gen_max_ec(ctx: GenContext):
    fam = "soil.max_ec"
    for (fk, year), (ss, ms) in sorted(_ec_by_field_year(ctx).items()):
        if len(ss) < 3:
            continue
        f = ctx.store.fields[fk]
        ranked = sorted(ss, key=lambda s: (-s.ec, s.key))
        if ranked[0].ec - ranked[1].ec < 0.02 * ranked[0].ec:
            ctx.skip(fam, "tie_at_top")
            continue
        labels = [s.label for s in ranked]
        if len(set(labels)) != len(labels):
            ctx.skip(fam, "ambiguous_sample_labels")
            continue
        rng = ctx.rng(f"{fam}:{fk}:{year}")
        others = ranked[1:]
        rng.shuffle(others)
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"أيّ عينات التربة التالية سجّلت أعلى ملوحة (EC) في الحقل {quote(f.display)} عام {year}؟",
            correct=ranked[0].label, distractors=[s.label for s in others[:3]], allow_abstain=False,
            evidence={"kind": "derived", "records": [field_ref(f)] + [sample_ref(s) for s in ss], "values": {s.label: s.ec for s in ranked},
                      "computation": "ترتيب العينات تنازلياً حسب EC؛ " + method_note(ms)},
            context=Cards().field(f, True).samples(ss), key={"field": fk, "year": year}, answer_value=ranked[0].label)
        if it:
            yield it


EC_CHANGE = ["ارتفع بأكثر من 100%", "ارتفع بنسبة بين 25% و100%", "تغيّر بأقل من 25% (شبه ثابت)", "انخفض بأكثر من 25%"]


def gen_ec_change(ctx: GenContext):
    fam = "temporal.ec_change"
    lo_band, hi_band = ctx.rules["ec_change_bands"]
    per_field = defaultdict(dict)
    for (fk, year), (ss, ms) in _ec_by_field_year(ctx).items():
        per_field[fk][year] = (ss, ms)
    for fk, years in sorted(per_field.items()):
        if len(years) < 2:
            continue
        y0, y1 = min(years), max(years)
        s0, s1 = years[y0][0], years[y1][0]
        m0, m1 = statistics.fmean(s.ec for s in s0), statistics.fmean(s.ec for s in s1)
        if m0 <= 0:
            continue
        rel = (m1 - m0) / m0
        if min(abs(rel - e) for e in (hi_band, lo_band, -lo_band)) < 0.03:
            ctx.skip(fam, "change_near_band_edge")
            continue
        idx = 0 if rel > hi_band else 1 if rel > lo_band else 2 if rel >= -lo_band else 3
        f = ctx.store.fields[fk]
        same_points = {s.sample_id for s in s0} & {s.sample_id for s in s1}
        caveats = [EC_CAVEAT] + ([] if same_points else ["العينات في السنتين من نقاط مختلفة؛ المقارنة على مستوى المتوسط فقط"])
        depths = {s.depth_cm for s in s0 + s1}
        if len(depths) > 1:
            caveats.append(f"أعماق أخذ العينات غير موحّدة: {sorted(d for d in depths if d is not None)}")
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=(f"كيف تغيّر متوسط ملوحة التربة (EC) في الحقل {quote(f.display)} بين عامي {y0} و{y1} "
                      "بحسب العينات المسجّلة؟"),
            correct=EC_CHANGE[idx], distractors=[t for i, t in enumerate(EC_CHANGE) if i != idx],
            evidence={"kind": "derived", "records": [field_ref(f)] + [sample_ref(s) for s in s0 + s1],
                      "values": {"mean_from": round(m0, 4), "mean_to": round(m1, 4), "relative_change": round(rel, 4),
                                 "n_from": len(s0), "n_to": len(s1)},
                      "computation": "(متوسط EC للسنة الأحدث − متوسط الأقدم) ÷ متوسط الأقدم", "caveats": caveats},
            context=Cards().field(f, True).samples(s0 + s1), key={"field": fk, "from": y0, "to": y1},
            answer_value=round(rel, 4))
        if it:
            yield it


def _index_series(ctx):
    """(field key, INDEX) -> [(date, daily_mean, [indicators])] — order independent."""
    pats = ctx.rules["indicator_patterns"]["vegetation"]
    raw = defaultdict(lambda: defaultdict(list))
    for f in ctx.store.fields.values():
        for ind, _ in ctx.store.indicators_for(f, pats):
            if ind.value is None or ind.recorded_ts is None:
                continue
            name = ind.indicator_id.split("_")[0].upper()
            raw[(f.key, name)][ind.recorded_at].append(ind)
    out = {}
    for k, days in raw.items():
        out[k] = [(d, statistics.fmean(i.value for i in inds), sorted(inds, key=lambda i: i.key))
                  for d, inds in sorted(days.items())]
    return dict(sorted(out.items()))


DAILY_NOTE = "عند تعدد الرصدات في اليوم نفسه تُستخدم قيمتها اليومية المتوسطة"


def _segments(series, max_gap_days: int = 60):
    """Split a dated series into seasons wherever observations are > max_gap apart
    (a winter season crossing New Year stays one segment)."""
    segs, cur = [], []
    for pt in series:
        if cur and (pt[0] - cur[-1][0]).days > max_gap_days:
            segs.append(cur)
            cur = []
        cur.append(pt)
    if cur:
        segs.append(cur)
    return segs


def _month_label(d) -> str:
    return f"{MONTHS[d.month - 1]} {d.year}"


def gen_index_peak(ctx: GenContext):
    fam = "temporal.index_peak"
    for (fk, name), series in _index_series(ctx).items():
        for pts in _segments(series):
            if len(pts) < 5:
                ctx.skip(fam, "season_too_short")
                continue
            ranked = sorted(pts, key=lambda t: (-t[1], t[0]))
            peak = _month_label(ranked[0][0])
            if ranked[0][1] - ranked[1][1] < 0.01 and _month_label(ranked[1][0]) != peak:
                ctx.skip(fam, "tie_at_peak")
                continue
            others = list(dict.fromkeys(_month_label(d) for d, _, _ in pts if _month_label(d) != peak))
            if len(others) < 2:
                ctx.skip(fam, "too_few_months")
                continue
            d0, d1 = pts[0][0], pts[-1][0]
            rng = ctx.rng(f"{fam}:{fk}:{name}:{d0}")
            rng.shuffle(others)
            f = ctx.store.fields[fk]
            inds = [i for _, _, day in pts for i in day]
            it = make_item(
                ctx, family=fam, level=LEVEL,
                question=(f"خلال الفترة من {d0} إلى {d1}، في أي شهر سجّل مؤشر {name} أعلى قيمة له "
                          f"في الحقل {quote(f.display)}؟"),
                correct=peak, distractors=others[:3], allow_abstain=False,
                evidence={"kind": "derived", "records": [field_ref(f)] + [indicator_ref(i) for i in inds],
                          "values": {"peak_date": str(ranked[0][0]), "peak_daily_value": round(ranked[0][1], 4),
                                     "n_days": len(pts), "n_records": len(inds)},
                          "computation": f"أعلى قيمة يومية لـ{name} في الموسم (الموسم = رصدات لا تفصلها فجوة > 60 يوماً)؛ {DAILY_NOTE}"},
                context=Cards().field(f, True).indicators(inds), key={"field": fk, "index": name, "from": str(d0), "to": str(d1)},
                answer_value=str(ranked[0][0]))
            if it:
                yield it


INDEX_TREND = ["ارتفع بأكثر من {hi}", "ارتفع بمقدار بين {lo} و{hi}", "تغيّر بأقل من {lo} (مستقر)", "انخفض بأكثر من {lo}"]


def gen_index_trend(ctx: GenContext):
    fam = "temporal.index_trend"
    lo, hi = ctx.rules["index_trend_bands"]
    labels = [t.format(lo=lo, hi=hi) for t in INDEX_TREND]
    for (fk, name), series in _index_series(ctx).items():
        made = 0
        for j in range(len(series) - 1, 0, -1):
            if made >= 4:
                break
            d1, v1, i1 = series[j]
            cands = [(abs((d1 - d0).days - 30), k) for k, (d0, _, _) in enumerate(series[:j]) if 20 <= (d1 - d0).days <= 45]
            if not cands:
                continue
            d0, v0, i0 = series[min(cands)[1]]
            delta = v1 - v0
            if min(abs(delta - e) for e in (hi, lo, -lo)) < 0.005:
                ctx.skip(fam, "delta_near_band_edge")
                continue
            idx = 0 if delta > hi else 1 if delta > lo else 2 if delta >= -lo else 3
            f = ctx.store.fields[fk]
            it = make_item(
                ctx, family=fam, level=LEVEL,
                question=f"كيف تغيّر مؤشر {name} في الحقل {quote(f.display)} بين يومي {d0} و{d1}؟",
                correct=labels[idx], distractors=[t for i, t in enumerate(labels) if i != idx],
                evidence={"kind": "derived", "records": [field_ref(f)] + [indicator_ref(i) for i in i0 + i1],
                          "values": {"from_daily": round(v0, 4), "to_daily": round(v1, 4), "delta": round(delta, 4)},
                          "computation": f"الفرق المطلق بين القيمتين اليوميتين لـ{name}؛ {DAILY_NOTE}"},
                context=Cards().field(f, True).indicators(i0 + i1),
                key={"field": fk, "index": name, "from": str(d0), "to": str(d1)}, answer_value=round(delta, 4))
            if it:
                made += 1
                yield it


def raster_stats(ctx: GenContext):
    """Cached polygon statistics for (field, layer) pairs that fully cover a field."""
    cache = ctx.cache.setdefault("raster", {})
    if "rows" in cache:
        return cache["rows"]
    rows = []
    for layer in ctx.store.rasters:
        if layer.role != "all":          # timeline-only layers feed the season-timeline families
            continue
        thr = ctx.rules["vegetation_threshold"].get(layer.index_name)
        if thr is None:
            continue
        for f in ctx.store.drawn_fields():
            st = polygon_stats(layer, f.geom, thr)
            if st is None:
                continue
            ok = st["full_cover"] and st["valid_frac"] >= 0.95 and st["pixels_in_polygon"] >= 50
            rows.append((f, layer, thr, st, ok))
    cache["rows"] = rows
    return rows


def image_ref(layer, f, thr) -> dict:
    from pathlib import Path
    return {"raster": Path(layer.path).name, "raster_key": layer.key, "scene_id": layer.scene_id,
            "index": layer.index_name, "date": str(layer.date), "crs": layer.crs, "field_key": f.key,
            "threshold": thr, "synthetic": layer.synthetic, "product_version": layer.product_version}


def image_legend(layer, thr, f) -> str:
    from ..raster import pixel_size_m, scale_bar_m
    return (f"الصورة: خريطة {layer.index_name} بتاريخ {layer.date} مصنّفة إلى فئتين — أخضر: {layer.index_name} ≥ {thr}، "
            f"بني: أقل من {thr}، رمادي: بلا بيانات صالحة؛ الخط الأصفر يحيط بالحقل من الخارج؛ الشمال إلى الأعلى (السهم الأبيض)؛ "
            f"شريط المقياس الأبيض = {scale_bar_m(layer, f.geom)} م؛ كل بكسل ≈ {pixel_size_m(layer, f.geom):.1f} م")


def gen_vegetation_fraction(ctx: GenContext):
    fam = "scene.vegetation_fraction"
    for f, layer, thr, st, ok in raster_stats(ctx):
        if not ok:
            ctx.skip(fam, "raster_does_not_cover_field")
            continue
        pct = 100 * st["frac_above"]
        correct, dists, meta = bin_options(pct, 0, "%", ctx.rng(f"{fam}:{f.key}:{layer.key}"), width=10, floor=0, ceil=100)
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=(f"في طبقة {layer.index_name} بتاريخ {layer.date}، ما نسبة مساحة الحقل {quote(f.display)} "
                      f"التي بلغت فيها قيمة {layer.index_name} {thr} أو أكثر؟"),
            correct=correct, distractors=dists,
            evidence={"kind": "derived", "records": [field_ref(f)], "values": {"pct_above": round(pct, 2), "threshold": thr,
                                                              "valid_pixels": st["valid_pixels"], "pixel_size": st["pixel_size"], **meta},
                      "computation": "البكسلات التي تقع مراكزها داخل المضلع وقيمتها ≥ العتبة ÷ البكسلات الصالحة × 100",
                      "synthetic_raster": layer.synthetic},
            context=Cards().field(f, True).text(image_legend(layer, thr, f)),
            key={"field": f.key, "raster": layer.key}, answer_value=round(pct, 2))
        if it:
            it["image_ref"] = image_ref(layer, f, thr)
            yield it


FAMILIES = {
    "scene.area": (LEVEL, gen_area),
    "scene.area_share": (LEVEL, gen_area_share),
    "scene.sample_count": (LEVEL, gen_sample_count),
    "scene.vegetation_fraction": (LEVEL, gen_vegetation_fraction),
    "soil.mean_ec": (LEVEL, gen_mean_ec),
    "soil.max_ec": (LEVEL, gen_max_ec),
    "temporal.ec_change": (LEVEL, gen_ec_change),
    "temporal.index_peak": (LEVEL, gen_index_peak),
    "temporal.index_trend": (LEVEL, gen_index_trend),
}

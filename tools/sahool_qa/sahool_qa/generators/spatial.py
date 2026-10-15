"""Level 1 — الإدراك المكاني: bounding box, relative direction, distance,
point-in-field. Pairs of fields are only formed within one tenant."""
from __future__ import annotations

from ..arabic import ltr_isolate, quote
from ..facts import tenant_key
from ..geo import DIRECTIONS_AR, direction_ambiguity, direction_index, vincenty_inverse
from ..items import GenContext, bin_options, make_item
from .common import Cards, field_ref, sample_ref

LEVEL = "spatial_perception"


def _bbox_text(b) -> str:
    return ltr_isolate("[" + ", ".join(f"{x:.5f}" for x in b) + "]")


def gen_bbox(ctx: GenContext):
    fam = "spatial.bbox"
    for f in ctx.store.drawn_fields():
        x0, y0, x1, y1 = f.geom.bbox
        ex, ey = x1 - x0, y1 - y0
        if ex < 1e-5 or ey < 1e-5:
            ctx.skip(fam, "degenerate_extent")
            continue
        rng = ctx.rng(f"{fam}:{f.key}")
        gt = (x0, y0, x1, y1)
        dists, tries = [], 0
        while len(dists) < 3 and tries < 200:
            tries += 1
            d = [gt[i] + rng.choice((-1, 1)) * rng.uniform(0.15, 0.35) * (ex if i % 2 == 0 else ey) * rng.choice((0, 1, 1))
                 for i in range(4)]
            if not (d[0] < d[2] and d[1] < d[3]):
                continue
            diff = max(abs(d[i] - gt[i]) / (ex if i % 2 == 0 else ey) for i in range(4))
            if diff < 0.12 or any(max(abs(d[i] - o[i]) / (ex if i % 2 == 0 else ey) for i in range(4)) < 0.08 for o in dists):
                continue
            dists.append(tuple(d))
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=(f"ما أصغر مستطيل موازٍ لمحوري الإحداثيات يضم حدود الحقل {quote(f.display)} بالكامل؟ "
                      "(الترتيب: أدنى خط طول، أدنى خط عرض، أعلى خط طول، أعلى خط عرض)"),
            correct=_bbox_text(gt), distractors=[_bbox_text(d) for d in dists],
            evidence={"kind": "derived", "records": [field_ref(f)], "values": {"bbox": list(gt)},
                      "computation": "أدنى وأعلى قيم خطوط الطول والعرض لرؤوس مضلع الحدود (ST_XMin/ST_YMin/ST_XMax/ST_YMax)"},
            context=Cards().field(f, True), key={"field": f.key, "bbox": [round(x, 6) for x in gt]},
            answer_value=list(gt))
        if it:
            yield it


def _pairs(ctx: GenContext, k: int = 3):
    fields = ctx.store.drawn_fields()
    cents = {f.key: f.geom.centroid for f in fields}
    for a in fields:
        others = []
        for b in fields:
            if b.key == a.key or tenant_key(b.tenant) != tenant_key(a.tenant):
                continue
            d, az = vincenty_inverse(*cents[a.key], *cents[b.key])
            others.append((d, az, b))
        others.sort(key=lambda t: (t[0], t[2].key))
        for d, az, b in others[:k]:
            yield a, b, d, az, cents[a.key], cents[b.key]


def gen_direction(ctx: GenContext):
    fam = "spatial.direction"
    for a, b, d, az, ca, cb in _pairs(ctx):
        if d < 100:
            ctx.skip(fam, "centroids_too_close")
            continue
        if direction_ambiguity(az) < 7.5:
            ctx.skip(fam, "bearing_near_sector_boundary")
            continue
        idx = direction_index(az)
        rng = ctx.rng(f"{fam}:{a.key}:{b.key}")
        dist_idx = [(idx + 4) % 8, (idx + rng.choice((2, -2))) % 8, (idx + rng.choice((1, -1))) % 8]
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"في أي اتجاه يقع مركز الحقل {quote(b.display)} بالنسبة إلى مركز الحقل {quote(a.display)}؟",
            correct=DIRECTIONS_AR[idx], distractors=[DIRECTIONS_AR[i] for i in dist_idx],
            evidence={"kind": "derived", "records": [field_ref(a), field_ref(b)],
                      "values": {"centroid_from": ca, "centroid_to": cb, "azimuth_deg": round(az, 2), "distance_m": round(d, 1)},
                      "computation": "سمت جيوديسي (Vincenty، WGS84) من مركز مساحة الأول إلى مركز مساحة الثاني، 8 قطاعات بعرض 45°",
                      "caveats": [] if direction_ambiguity(az) > 12 else ["السمت قريب من حدّ قطاع (ضمن 12°)"]},
            context=Cards().field(a, True).field(b, True), key={"from": a.key, "to": b.key}, answer_value=round(az, 2))
        if it:
            yield it


def gen_distance(ctx: GenContext):
    fam = "spatial.distance"
    seen = set()
    for a, b, d, az, ca, cb in _pairs(ctx):
        pair = tuple(sorted((a.key, b.key)))
        if pair in seen:
            continue
        seen.add(pair)
        if d < 50:
            ctx.skip(fam, "centroids_too_close")
            continue
        rng = ctx.rng(f"{fam}:{pair}")
        if d < 5000:
            correct, dists, meta = bin_options(d, 0.12, "م", rng, min_width=50)
        else:
            correct, dists, meta = bin_options(d / 1000, 0.12, "كم", rng, min_width=0.5)
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"كم تبلغ المسافة التقريبية بين مركزي الحقلين {quote(a.display)} و{quote(b.display)}؟",
            correct=correct, distractors=dists,
            evidence={"kind": "derived", "records": [field_ref(a), field_ref(b)],
                      "values": {"distance_m": round(d, 1), "centroid_a": ca, "centroid_b": cb, **meta},
                      "computation": "مسافة جيوديسية (Vincenty على إهليلج WGS84) بين مركزي مساحة المضلعين"},
            context=Cards().field(a, True).field(b, True), key={"pair": list(pair)}, answer_value=round(d, 1))
        if it:
            yield it


def gen_point_in_field(ctx: GenContext):
    fam = "spatial.point_in_field"
    tol = ctx.store.boundary_tolerance_m
    for f in ctx.store.drawn_fields():
        pts = [s for s in ctx.store.soil if s.point is not None and tenant_key(s.tenant) == tenant_key(f.tenant)]
        labels = {}
        for s in pts:
            labels.setdefault(s.label, []).append(s)
        pts = [s for s in pts if len(labels[s.label]) == 1]          # option labels must be unambiguous
        pts = [s for s in pts if f.geom.boundary_distance_m(*s.point) >= tol]   # no GPS-ambiguous points
        inside = [s for s in pts if f.geom.contains(*s.point)]
        outside = [s for s in pts if not f.geom.contains(*s.point)]
        if not inside or len(outside) < 2:
            ctx.skip(fam, "not_enough_inside_outside_points")
            continue
        c = f.geom.centroid
        outside.sort(key=lambda s: (vincenty_inverse(*c, *s.point)[0], s.key))
        rng = ctx.rng(f"{fam}:{f.key}")
        pick = rng.choice(inside)
        dist = outside[:3]
        it = make_item(
            ctx, family=fam, level=LEVEL,
            question=f"أيّ عينات التربة التالية تقع نقطتها داخل حدود الحقل {quote(f.display)}؟",
            correct=pick.label, distractors=[s.label for s in dist], allow_abstain=False,
            evidence={"kind": "derived", "records": [field_ref(f)] + [sample_ref(s) for s in [pick, *dist]],
                      "values": {"inside": pick.label, "outside": [s.label for s in dist],
                                 "boundary_distance_m": {s.label: round(f.geom.boundary_distance_m(*s.point), 1)
                                                         for s in [pick, *dist]}},
                      "computation": f"ST_Contains لكل نقطة؛ استُبعدت النقاط الأقرب من {tol:g} م إلى الحد"},
            context=Cards().field(f, True).samples([pick, *dist]),
            key={"field": f.key, "inside": pick.key, "outside": sorted(s.key for s in dist)}, answer_value=pick.label)
        if it:
            yield it


FAMILIES = {
    "spatial.bbox": (LEVEL, gen_bbox),
    "spatial.direction": (LEVEL, gen_direction),
    "spatial.distance": (LEVEL, gen_distance),
    "spatial.point_in_field": (LEVEL, gen_point_in_field),
}

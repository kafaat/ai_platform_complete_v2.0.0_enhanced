"""Data-quality audit. Runs BEFORE question generation on a prepared store
(QC applied, invalid geometry quarantined), so a bad row can neither crash
the run nor turn into a confident answer; every problem is written to
data_issues.jsonl. Field references use the composite key "<tenant>::<field_id>"."""
from __future__ import annotations

from collections import defaultdict

from .facts import FactStore
from .waterbal import coverage_problem, field_water, instrument_problem, meter_owners, meter_sequence_problem


def _issue(code, severity, message, **ref):
    return {"code": code, "severity": severity, "message": message, **ref}


QC_MESSAGES = {
    "value_not_finite": "قيمة غير منتهية (NaN/Infinity) — استُبعدت",
    "ph_out_of_range": "قيمة pH خارج المدى المعقول — استُبعدت",
    "ec_out_of_range": "قيمة EC خارج المدى المعقول (هل الوحدة µS/cm؟) — استُبعدت",
    "index_out_of_range": "مؤشر نباتي خارج المدى [-1، 1] — استُبعد",
    "unknown_ec_unit": "وحدة EC غير معروفة فلا يمكن تحويلها إلى dS/m",
    "unknown_unit": "وحدة غير مقبولة لهذا النوع من سجلات الماء فلا تُستخدم",
    "value_out_of_range": "قيمة خارج المدى المعقول لنوعها — استُبعدت",
    "volume_meter_stalled": "عداد الساعات تقدم وعداد الماء لم يتقدم، دون سجل حالة يثبت خروج البئر من الخدمة",
    "hour_meter_stalled": "عداد الماء تقدم وعداد الساعات لم يتقدم",
    "well_status_conflict": "عداد الماء تقدم بينما سجل الحالة يقول إن البئر خارج الخدمة",
}


def audit(store: FactStore, rules: dict) -> list[dict]:
    issues = []
    bx0, by0, bx1, by1 = rules["country_bbox"]
    tol = store.boundary_tolerance_m

    def outside_country(lon, lat):
        return not (bx0 <= lon <= bx1 and by0 <= lat <= by1)

    def swapped(lon, lat):
        return outside_country(lon, lat) and not outside_country(lat, lon)

    for reason, n in sorted(store.rejected.items()):
        issues.append(_issue(f"rejected_{reason}", "warning",
                             f"{n} سجلاً لم تُقبل ({reason}): خارج نطاق المستأجر أو بلا حقل مالك من المستأجر نفسه",
                             count=n))
    for f in store.fields.values():
        ref = {"field_id": f.key}
        if f.geom_problems:
            issues.append(_issue("invalid_polygon", "error", "مضلع غير صالح، عُزل عن الأسئلة: " + "؛ ".join(f.geom_problems), **ref))
        elif f.geom is None:
            issues.append(_issue("field_no_polygon", "warning",
                                 "الحقل بلا حدود مرسومة؛ أسئلة الشكل والاتجاه غير ممكنة له", **ref))
        if f.geom is not None:
            g = f.geom
            if g.extent_warning():
                issues.append(_issue("polygon_too_large", "warning",
                                     "امتداد المضلع أكبر من 50 كم؛ دقة الإطار المحلي للمساحة تنخفض", **ref))
            ha = g.area_m2 / 1e4
            if f.area_ha_stored and ha > 0 and abs(f.area_ha_stored / ha - 1) > 0.05:
                issues.append(_issue("area_mismatch", "error",
                                     f"المساحة المسجّلة {f.area_ha_stored} هكتار لا تطابق مساحة المضلع {ha:.3f} هكتار "
                                     f"(النسبة {f.area_ha_stored / ha:.3g})", stored_ha=f.area_ha_stored,
                                     polygon_ha=round(ha, 4), **ref))
            if f.db_area_m2:
                rel = abs(f.db_area_m2 - g.area_m2) / f.db_area_m2
                if rel > 0.0005:
                    issues.append(_issue("area_engine_mismatch", "warning",
                                         f"مساحة PostGIS ({f.db_area_m2:.1f} م²) تختلف عن حساب المولّد بنسبة {rel:.3%}", **ref))
            cx, cy = g.centroid
            if outside_country(cx, cy):
                issues.append(_issue("geometry_outside_country", "error",
                                     "مركز المضلع خارج حدود اليمن" + (" — يبدو أن خطي الطول والعرض مقلوبان" if swapped(cx, cy) else ""),
                                     **ref))
            if f.lat is not None and f.lon is not None and not g.contains(f.lon, f.lat):
                issues.append(_issue("location_point_outside_polygon", "info",
                                     "نقطة الموقع (latitude/longitude) تقع خارج الحدود المرسومة", **ref))
        if f.lat is not None and f.lon is not None and outside_country(f.lon, f.lat):
            issues.append(_issue("location_outside_country", "error",
                                 "نقطة موقع الحقل خارج حدود اليمن" + (" — يبدو أن القيمتين مقلوبتان" if swapped(f.lon, f.lat) else ""),
                                 **ref))

    drawn = store.drawn_fields()
    by_loc = defaultdict(list)
    for s in store.soil:
        ref = {"field_id": s.field_key, "sample_id": s.sample_id,
               "recorded_at": s.recorded_ts.isoformat() if s.recorded_ts else None}
        for attr, q in sorted(s.qc.items()):
            code = q["code"] if q["code"] != "value_not_finite" else "value_not_finite"
            issues.append(_issue(code, "error", f"{attr}: {QC_MESSAGES.get(code, code)} (القيمة الخام {q['raw']})",
                                 attribute=attr, **ref))
        if s.recorded_ts is None:
            issues.append(_issue("sample_no_date", "warning", "عينة بلا تاريخ؛ تُستبعد من الأسئلة الزمنية", **ref))
        if all(getattr(s, a) is None for a in ("ph", "ec", "n", "p", "k", "om", "moisture")) and not s.qc:
            issues.append(_issue("sample_empty", "warning", "عينة بلا أي قيمة مقاسة", **ref))
        if s.point is not None:
            if outside_country(*s.point):
                issues.append(_issue("sample_outside_country", "error",
                                     "نقطة العينة خارج حدود اليمن" + (" — القيمتان مقلوبتان على الأرجح" if swapped(*s.point) else ""), **ref))
            own = store.fields.get(s.field_key)
            if own is not None and own.geom is not None and not own.geom.contains(*s.point):
                issues.append(_issue("sample_outside_own_field", "warning", "نقطة العينة خارج حدود الحقل المسجّلة له", **ref))
            for f in drawn:
                if f.tenant == s.tenant and f.geom.boundary_distance_m(*s.point) < tol:
                    issues.append(_issue("sample_near_boundary", "warning",
                                         f"نقطة العينة على بعد أقل من {tol:g} م من حدود {f.display}؛ لا تُنسب مكانياً إلى الحقل",
                                         near_field=f.key, **ref))
            by_loc[(s.tenant, round(s.point[0], 7), round(s.point[1], 7), s.recorded_at)].append(s)
    for (tenant, lon, lat, d), ss in by_loc.items():
        ids = sorted({s.sample_id for s in ss})
        if len(ids) > 1:
            issues.append(_issue("duplicate_sample_location", "warning",
                                 f"عينات مختلفة بالإحداثيات نفسها والتاريخ نفسه: {', '.join(ids)} — تحقّق من نسخ الإحداثيات",
                                 sample_ids=ids, location=[lon, lat], recorded_at=str(d), tenant=tenant))
    for ind in store.indicators:
        for attr, q in ind.qc.items():
            issues.append(_issue(q["code"], "warning" if q["code"] in ("unknown_ec_unit", "unknown_unit") else "error",
                                 f"{ind.indicator_id}: {QC_MESSAGES.get(q['code'], q['code'])} (القيمة {q['raw']}، الوحدة {ind.unit!r})",
                                 field_id=ind.field_key, indicator_id=ind.indicator_id,
                                 recorded_at=ind.recorded_ts.isoformat() if ind.recorded_ts else None))

    # water records (0.4.0): cumulative meters that go down, meters recorded under several fields
    for (tenant, mid), owners in sorted(meter_owners(store, rules).items()):
        if len(owners) > 1:
            issues.append(_issue("meter_shared_between_fields", "warning",
                                 f"العداد {mid} مسجّل لأكثر من حقل؛ لا يمكن قسمة حجمه بينها دون سجل صمامات",
                                 indicator_id=mid, field_ids=owners, tenant=tenant))
    for f in store.fields.values():
        fw = field_water(store, f, rules)
        span = fw.all_days()
        if span and fw.of("meter"):
            problem, detail = coverage_problem(store, fw, rules, span[0], span[-1])
            if problem:
                issues.append(_issue(problem, "warning", "تغطية مصادر ري الحقل غير مكتملة أو غير مثبتة",
                                     field_id=f.key, detail=detail))
        for well, ms in fw.of("meter").items():
            days = ms.days()
            if len(days) > 1:
                problem, detail = instrument_problem(fw, well, days[0], days[-1], rules)
                if problem:
                    issues.append(_issue(problem, "warning", f"{ms.indicator_id}: {QC_MESSAGES[problem]} ({detail})",
                                         field_id=f.key, indicator_id=ms.indicator_id, detail=detail))
        for kind in ("meter", "pump_hours"):
            for s in fw.of(kind).values():
                rows = sorted((r for rs in s.records.values() for r in rs if r.conv is not None),
                              key=lambda r: (r.recorded_ts, r.key))
                for x, y in zip(rows, rows[1:]):
                    problem = meter_sequence_problem([x, y])
                    if problem:
                        issues.append(_issue("cumulative_meter_decrease" if problem == "meter_decrease" else problem,
                                             "warning", f"{s.indicator_id}: {problem}; period volume unknown",
                                             field_id=f.key, indicator_id=s.indicator_id,
                                             recorded_at=str(y.recorded_at),
                                             timestamp=y.recorded_ts.isoformat(), previous=x.conv, current=y.conv))
    return issues

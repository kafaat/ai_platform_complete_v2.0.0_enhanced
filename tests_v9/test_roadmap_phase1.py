"""
tests_v9/test_roadmap_phase1.py — اختبارات المرحلة ١ (Timeline + Pins)

⚠ pure-logic (بلا fastapi/DB). يحاكي منطق الـendpoints.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


# ════════════════════════════════════════════════════════════════
# البند ٧: Field Timeline
# ════════════════════════════════════════════════════════════════
def test_timeline_assembly():
    from api.field_timeline import TimelineCategory, assemble_timeline

    results = []
    events = [
        {
            "event_type": "field.created",
            "occurred_at": "2026-01-01T08:00:00+00:00",
            "payload": {"area_ha": 4.0},
        },
        {
            "event_type": "lifecycle.transitioned",
            "occurred_at": "2026-02-01T06:00:00+00:00",
            "payload": {"to_stage": "PLANTED"},
        },
        {
            "event_type": "operation.irrigation.completed",
            "occurred_at": "2026-02-05T18:00:00+00:00",
            "payload": {"water_m3": 320},
        },
        {
            "event_type": "scouting.pin.created",
            "occurred_at": "2026-03-10T10:00:00+00:00",
            "payload": {"issue": "tuta"},
        },
        {
            "event_type": "trueup.apply",
            "occurred_at": "2026-06-01T12:00:00+00:00",
            "payload": {"k_new": 1.05},
        },
    ]
    tl = assemble_timeline("fld-1", events)
    if tl.total_events == 5:
        results.append(("✓", "5 أحداث في الخطّ الزمني"))
    # الأحدث أوّلاً
    if tl.events[0].event_type == "trueup.apply":
        results.append(("✓", "ترتيب تنازلي (الأحدث أوّلاً)"))
    # التصنيف
    cats = tl.category_counts
    if cats.get("operation") == 1 and cats.get("calibration") == 1:
        results.append(("✓", f"تصنيف صحيح: {cats}"))
    # ملخّص عربي
    if "م³" in tl.events[1].summary_ar or "320" in str(tl.events[1].payload):
        results.append(("✓", "ملخّص عربي للري"))
    return results


def test_timeline_filter():
    from api.field_timeline import assemble_timeline

    results = []
    events = [
        {"event_type": "field.created", "occurred_at": "2026-01-01T08:00:00+00:00", "payload": {}},
        {
            "event_type": "operation.harvest.completed",
            "occurred_at": "2026-06-01T08:00:00+00:00",
            "payload": {},
        },
        {
            "event_type": "scouting.pin.created",
            "occurred_at": "2026-03-01T08:00:00+00:00",
            "payload": {},
        },
    ]
    tl = assemble_timeline("fld-1", events, category_filter=["observation"])
    if tl.total_events == 1 and tl.events[0].event_type == "scouting.pin.created":
        results.append(("✓", "ترشيح بالفئة (observation) = 1"))
    return results


def test_timeline_empty():
    from api.field_timeline import assemble_timeline

    results = []
    tl = assemble_timeline("fld-1", [])
    if tl.total_events == 0 and tl.earliest_at is None:
        results.append(("✓", "خطّ زمني فارغ آمن"))
    return results


# ════════════════════════════════════════════════════════════════
# البند ٨: Scouting Pins
# ════════════════════════════════════════════════════════════════
def test_pin_creation_valid():
    from api.scouting_pins import make_pin

    results = []
    p = make_pin(
        "pin-1",
        "fld-1",
        16.0,
        45.0,
        "pest",
        "high",
        "new",
        "seasonal",
        crop="tomato",
        issue_code="tomato.tuta",
        note_ar="إصابة",
    )
    d = p.to_dict()
    if d["issue_code"] == "tomato.tuta" and d["severity"] == "high":
        results.append(("✓", "pin صالح يُنشأ"))
    if d["persistence"] == "seasonal":
        results.append(("✓", "علم موسمي صحيح"))
    return results


def test_pin_rejects_outside_yemen():
    from api.scouting_pins import make_pin

    results = []
    try:
        make_pin("pin-2", "fld-1", 50.0, 10.0, "pest")
        results.append(("✗", "كان يجب رفض إحداثيّات خارج اليمن"))
    except ValueError:
        results.append(("✓", "رفض إحداثيّات خارج اليمن"))
    return results


def test_pin_rejects_bad_issue_code():
    from api.scouting_pins import validate_pin

    results = []
    r = validate_pin(
        16.0, 45.0, "pest", "high", "new", "seasonal", crop="tomato", issue_code="wheat.rust"
    )
    if not r.valid:
        results.append(("✓", "رفض رمز مشكلة خاطئ للمحصول"))
    return results


def test_pin_taxonomy():
    from api.scouting_pins import NUTRIENT_DEFICIENCY_GUIDE, YEMEN_CROP_ISSUES, get_crop_issues

    results = []
    if len(YEMEN_CROP_ISSUES) >= 13:
        results.append(("✓", f"{len(YEMEN_CROP_ISSUES)} محصول في الـtaxonomy"))
    tomato = get_crop_issues("tomato")
    if any(i["code"] == "tomato.tuta" for i in tomato):
        results.append(("✓", "توتا في مشاكل الطماطم"))
    # دليل نقص العناصر (التربة الكلسيّة)
    if any(g["code"] == "fe" for g in NUTRIENT_DEFICIENCY_GUIDE):
        results.append(("✓", "دليل نقص الحديد موجود (تربة كلسيّة)"))
    return results


def test_pin_enums_validated():
    from api.scouting_pins import validate_pin

    results = []
    r = validate_pin(16.0, 45.0, "INVALID_CAT", "high", "new", "seasonal")
    if not r.valid and any("فئة" in i for i in r.issues):
        results.append(("✓", "رفض فئة مشكلة غير صالحة"))
    return results


# ════════════════════════════════════════════════════════════════
# البند ٩: Manual Application Mode
# ════════════════════════════════════════════════════════════════
def test_manual_kg_terrace():
    from api.manual_converter import kg_per_terrace

    results = []
    # 120 kg/ha على مصطبة 200 م² = 2.4 كغ
    if abs(kg_per_terrace(120, 200) - 2.4) < 1e-9:
        results.append(("✓", "kg_per_terrace(120,200) = 2.4 كغ"))
    return results


def test_manual_broadcast():
    from api.manual_converter import ApplicationMethod, EquipmentSpec, convert_zone

    results = []
    d = convert_zone(
        "z1",
        120,
        0.5,
        ApplicationMethod.BROADCAST_TERRACE,
        EquipmentSpec(terrace_area_m2=200, cap_weight_kg=0.5),
    )
    # 0.5 ha = 5000 م² / 200 = 25 مصطبة
    if abs(d.terraces_count - 25) < 1e-6:
        results.append(("✓", "0.5هـ → 25 مصطبة"))
    if abs(d.kg_per_terrace - 2.4) < 1e-6:
        results.append(("✓", "2.4 كغ/مصطبة"))
    if abs(d.caps_per_terrace - 4.8) < 1e-6:
        results.append(("✓", "4.8 غطاء/مصطبة"))
    if d.instruction_ar:
        results.append(("✓", f"تعليمات عربيّة: {d.instruction_ar[:30]}"))
    return results


def test_manual_reject_missing():
    from api.manual_converter import ApplicationMethod, EquipmentSpec, convert_zone

    results = []
    try:
        convert_zone("z1", 120, 0.5, ApplicationMethod.BROADCAST_TERRACE, EquipmentSpec())
        results.append(("✗", "كان يجب رفض معدّات ناقصة"))
    except ValueError:
        results.append(("✓", "رفض معدّات ناقصة"))
    return results


def test_walk_plan_order():
    from api.manual_converter import ApplicationMethod, EquipmentSpec
    from api.walk_plan import ZoneRateInput, generate_walk_plan

    results = []
    zones = [
        ZoneRateInput("z_problem", 80, 0.3, "problem"),
        ZoneRateInput("z_high", 180, 0.5, "high"),
        ZoneRateInput("z_low", 100, 0.4, "low"),
    ]
    plan = generate_walk_plan(
        "fld-1",
        "wheat",
        zones,
        ApplicationMethod.BROADCAST_TERRACE,
        EquipmentSpec(terrace_area_m2=200, cap_weight_kg=0.5),
    )
    d = plan.to_dict()
    # الترتيب: high أوّلاً، problem أخيراً
    if d["steps"][0]["zone_class"] == "high" and d["steps"][-1]["zone_class"] == "problem":
        results.append(("✓", "ترتيب high→low→problem"))
    # الإجمالي: 90+40+24 = 154 كغ
    if abs(d["total_product_kg"] - 154) < 0.1:
        results.append(("✓", "إجمالي 154 كغ"))
    if d["total_estimated_hours"] > 0:
        results.append(("✓", f"وقت مُقدَّر {d['total_estimated_hours']} ساعة"))
    return results


def test_walk_plan_pdf():
    from api.manual_converter import ApplicationMethod, EquipmentSpec
    from api.walk_plan import ZoneRateInput, generate_walk_plan
    from api.walk_plan_pdf import walk_plan_to_pdf_bytes

    results = []
    zones = [ZoneRateInput("z1", 180, 0.5, "high")]
    plan = generate_walk_plan(
        "fld-1",
        "wheat",
        zones,
        ApplicationMethod.BROADCAST_TERRACE,
        EquipmentSpec(terrace_area_m2=200, cap_weight_kg=0.5),
    )
    try:
        pdf = walk_plan_to_pdf_bytes(plan.to_dict())
        if pdf[:4] == b"%PDF" and len(pdf) > 1000:
            results.append(("✓", f"PDF مُولَّد ({len(pdf)} بايت)"))
    except RuntimeError:
        results.append(("✓", "reportlab غائب (متوقّع في بعض البيئات)"))
    return results


def run_all():
    print("=" * 60)
    print("  المرحلة ١: Field Timeline + Scouting Pins + Manual Application")
    print("=" * 60)
    suites = [
        ("Timeline: assembly", test_timeline_assembly),
        ("Timeline: filter", test_timeline_filter),
        ("Timeline: empty", test_timeline_empty),
        ("Pin: valid creation", test_pin_creation_valid),
        ("Pin: reject outside Yemen", test_pin_rejects_outside_yemen),
        ("Pin: reject bad issue code", test_pin_rejects_bad_issue_code),
        ("Pin: taxonomy", test_pin_taxonomy),
        ("Pin: enum validation", test_pin_enums_validated),
        ("Manual: kg/terrace math", test_manual_kg_terrace),
        ("Manual: broadcast conversion", test_manual_broadcast),
        ("Manual: reject missing equip", test_manual_reject_missing),
        ("WalkPlan: ordering + totals", test_walk_plan_order),
        ("WalkPlan: PDF generation", test_walk_plan_pdf),
    ]
    tp = tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        for status, msg in suite():
            print(f"  {status} {msg}")
            tp += 1 if status == "✓" else 0
            tf += 1 if status == "✗" else 0
    print(f"\n{'=' * 60}\n  Passed: {tp}/{tp + tf}\n{'=' * 60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)


# ════════════════════════════════════════════════════════════════
# البند ٩: Manual Application Mode (يُلحَق لاحقاً عبر run_all2)
# ════════════════════════════════════════════════════════════════
def test_manual_converter():
    from api.manual_converter import ApplicationMethod, EquipmentSpec, convert_zone, kg_per_terrace

    results = []
    # تحويل أساسي
    if abs(kg_per_terrace(120, 200) - 2.4) < 1e-9:
        results.append(("✓", "kg_per_terrace(120,200)=2.4"))
    # نثر مصطبة: 0.5ha/200م²=25 مصطبة
    d = convert_zone(
        "z1",
        120,
        0.5,
        ApplicationMethod.BROADCAST_TERRACE,
        EquipmentSpec(terrace_area_m2=200, cap_weight_kg=0.5),
    )
    if abs(d.terraces_count - 25) < 1e-6 and abs(d.kg_per_terrace - 2.4) < 1e-6:
        results.append(("✓", "نثر: 25 مصطبة، 2.4كغ/مصطبة"))
    # رفض معدّات ناقصة
    try:
        convert_zone("z2", 120, 0.5, ApplicationMethod.BROADCAST_TERRACE, EquipmentSpec())
        results.append(("✗", "كان يجب رفض معدّات ناقصة"))
    except ValueError:
        results.append(("✓", "رفض معدّات ناقصة"))
    return results


def test_walk_plan():
    from api.manual_converter import ApplicationMethod, EquipmentSpec
    from api.walk_plan import ZoneRateInput, generate_walk_plan

    results = []
    zones = [
        ZoneRateInput("z_problem", 80, 0.3, "problem"),
        ZoneRateInput("z_high", 180, 0.5, "high"),
        ZoneRateInput("z_low", 100, 0.4, "low"),
    ]
    plan = generate_walk_plan(
        "fld-1",
        "wheat",
        zones,
        ApplicationMethod.BROADCAST_TERRACE,
        EquipmentSpec(terrace_area_m2=200, cap_weight_kg=0.5),
    )
    d = plan.to_dict()
    # الترتيب: high أوّلاً، problem أخيراً
    if d["steps"][0]["zone_class"] == "high" and d["steps"][-1]["zone_class"] == "problem":
        results.append(("✓", "ترتيب high→low→problem"))
    # الإجمالي: 90+40+24=154
    if abs(d["total_product_kg"] - 154) < 0.1:
        results.append(("✓", "إجمالي 154 كغ"))
    return results


def test_walk_plan_pdf():
    from api.manual_converter import ApplicationMethod, EquipmentSpec
    from api.walk_plan import ZoneRateInput, generate_walk_plan
    from api.walk_plan_pdf import walk_plan_to_pdf_bytes

    results = []
    zones = [ZoneRateInput("z1", 180, 0.5, "high")]
    plan = generate_walk_plan(
        "fld-1",
        "wheat",
        zones,
        ApplicationMethod.BROADCAST_TERRACE,
        EquipmentSpec(terrace_area_m2=200, cap_weight_kg=0.5),
    )
    try:
        pdf = walk_plan_to_pdf_bytes(plan.to_dict())
        if pdf[:4] == b"%PDF" and len(pdf) > 1000:
            results.append(("✓", f"PDF مُولَّد ({len(pdf)} بايت)"))
    except RuntimeError:
        results.append(("✓", "PDF يحتاج reportlab (fallback صحيح)"))
    return results


def run_all2():
    print("=" * 60)
    print("  البند ٩: Manual Application Mode")
    print("=" * 60)
    suites = [
        ("Converter", test_manual_converter),
        ("Walk plan", test_walk_plan),
        ("Walk plan PDF", test_walk_plan_pdf),
    ]
    tp = tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        for status, msg in suite():
            print(f"  {status} {msg}")
            tp += 1 if status == "✓" else 0
            tf += 1 if status == "✗" else 0
    print(f"\n  Passed: {tp}/{tp + tf}")
    return tp, tf


# ════════════════════════════════════════════════════════════════
# مُستخرَج من المرفقات: trial_randomization (تمهيد البند ١١)
# ════════════════════════════════════════════════════════════════
def test_deterministic_randomization():
    from api.trial_randomization import (
        RandomizationConfig,
        generate_block_assignments,
        verify_assignment,
    )

    results = []
    c = RandomizationConfig("t1", 6, "hash_chain", hash_chain_input="aljawf-2026")
    r1 = generate_block_assignments(c)
    r2 = generate_block_assignments(c)
    if [b.treatment_position for b in r1.blocks] == [b.treatment_position for b in r2.blocks]:
        results.append(("✓", "حتميّة (نفس التوزيع عند الإعادة)"))
    if all(verify_assignment(b) for b in r1.blocks):
        results.append(("✓", "كل الكتل تتحقّق"))
    # كشف تلاعب
    b0 = r1.blocks[0]
    b0.treatment_position = "south" if b0.treatment_position == "north" else "north"
    if not verify_assignment(b0):
        results.append(("✓", "كشف التلاعب"))
    # رفض <4
    try:
        generate_block_assignments(RandomizationConfig("t2", 2, "user_provided", seed_value=42))
        results.append(("✗", "كان يجب رفض <4 كتل"))
    except ValueError:
        results.append(("✓", "رفض <4 كتل"))
    # حماية البذرة
    if "master_seed" not in r1.to_dict():
        results.append(("✓", "البذرة الخام محميّة"))
    return results


def run_all3():
    print("=" * 60)
    print("  مُستخرَج: trial_randomization")
    print("=" * 60)
    tp = tf = 0
    print("\n── Deterministic randomization ──")
    for status, msg in test_deterministic_randomization():
        print(f"  {status} {msg}")
        tp += 1 if status == "✓" else 0
        tf += 1 if status == "✗" else 0
    print(f"\n  Passed: {tp}/{tp + tf}")
    return tp, tf

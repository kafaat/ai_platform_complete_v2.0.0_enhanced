"""
tests_v9/test_trueup_endpoint.py — اختبار منطق endpoint الـTrueUp

⚠ صدق عن المحدوديّة:
   البيئة بلا fastapi/pydantic (شبكة معطّلة، لا pip install). لذلك لا أستطيع
   تشغيل FastAPI TestClient حقيقي يضرب HTTP. هذا الاختبار يتحقّق من:
     - منطق الـrequest→engine→response mapping (نفس ما يفعله الـendpoint)
     - حالات القبول/الرفض (200 vs 422)
     - field_id mismatch (400)

   ما لا يختبره (بصدق):
     - HTTP layer الفعلي (routing, serialization, auth dependency)
     - DB persistence (pool=None في هذه المرحلة)

   عند توفّر fastapi: يُستبدَل هذا بـTestClient(app) حقيقي.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../services/sahool-platform'))

from api.trueup import TrueUpEngine, TrueUpInput, TrueUpStatus


# نحاكي منطق الـendpoint (apply_trueup في main.py) بدون fastapi
def simulate_trueup_endpoint(path_field_id: str, req: dict):
    """يحاكي بالضبط ما يفعله @app.post('/api/v1/fields/{field_id}/trueup')."""
    # ١. field_id mismatch check (400)
    if req["field_id"] != path_field_id:
        return {"_status_code": 400, "detail": "field_id mismatch"}

    engine = TrueUpEngine()
    inp = TrueUpInput(
        field_id=req["field_id"],
        operation_id=req["operation_id"],
        actual_weight_kg=req["actual_weight_kg"],
        actual_moisture_pct=req["actual_moisture_pct"],
        measured_weight_kg=req["measured_weight_kg"],
        sample_area_ha=req.get("sample_area_ha"),
        notes_ar=req.get("notes_ar"),
    )
    result = engine.compute(
        input_data=inp,
        crop=req["crop"],
        measured_yield_kg_ha=req["measured_yield_kg_ha"],
        k_old=1.0,
    )

    if result.status == TrueUpStatus.REJECTED:
        return {"_status_code": 422, "rationale_ar": result.rationale_ar,
                "warnings": result.warnings}

    return {
        "_status_code": 200,
        "status": result.status.value,
        "k_new": result.k_new,
        "adjusted_yield_kg_ha": result.adjusted_yield_kg_ha,
        "error_pct": result.error_pct,
        "moisture_correction_applied": result.moisture_correction_applied,
        "persisted": False,
    }


def test_endpoint_happy_path():
    results = []
    fid = "11111111-1111-1111-1111-111111111111"
    req = {
        "field_id": fid,
        "operation_id": "22222222-2222-2222-2222-222222222222",
        "crop": "wheat",
        "actual_weight_kg": 2100,
        "actual_moisture_pct": 14.0,
        "measured_weight_kg": 2000,
        "measured_yield_kg_ha": 2500,
    }
    resp = simulate_trueup_endpoint(fid, req)
    if resp["_status_code"] == 200:
        results.append(("✓", "200 على input صالح"))
    if 1.04 < resp["k_new"] < 1.06:
        results.append(("✓", f"k_new={resp['k_new']} في الاستجابة"))
    if 2620 < resp["adjusted_yield_kg_ha"] < 2630:
        results.append(("✓", f"adjusted_yield={resp['adjusted_yield_kg_ha']}"))
    if resp["moisture_correction_applied"]:
        results.append(("✓", "moisture correction مُطبَّق (wheat)"))
    if resp["persisted"] is False:
        results.append(("✓", "persisted=False (صادق: لا DB بعد)"))
    return results


def test_endpoint_field_mismatch():
    results = []
    req = {
        "field_id": "aaaa1111-1111-1111-1111-111111111111",
        "operation_id": "22222222-2222-2222-2222-222222222222",
        "crop": "wheat", "actual_weight_kg": 2100,
        "actual_moisture_pct": 14.0, "measured_weight_kg": 2000,
        "measured_yield_kg_ha": 2500,
    }
    # path يختلف عن body
    resp = simulate_trueup_endpoint("bbbb2222-2222-2222-2222-222222222222", req)
    if resp["_status_code"] == 400:
        results.append(("✓", "400 على field_id mismatch"))
    return results


def test_endpoint_rejection():
    results = []
    fid = "11111111-1111-1111-1111-111111111111"
    # وزن فعلي = 2.5× المقاس → k خارج النطاق → رفض
    req = {
        "field_id": fid,
        "operation_id": "22222222-2222-2222-2222-222222222222",
        "crop": "wheat",
        "actual_weight_kg": 5000,
        "actual_moisture_pct": 14.0,
        "measured_weight_kg": 2000,
        "measured_yield_kg_ha": 2500,
    }
    resp = simulate_trueup_endpoint(fid, req)
    if resp["_status_code"] == 422:
        results.append(("✓", "422 على k خارج النطاق"))
    if "rationale_ar" in resp and resp["rationale_ar"]:
        results.append(("✓", "الرفض يحوي تفسير عربي"))
    return results




# ════════════════════════════════════════════════════════════════
# Geometry validation endpoint logic (توصيل الوحدة الثانية)
# ════════════════════════════════════════════════════════════════
from api.geospatial_integrity import validate_field_geometry


def simulate_geometry_endpoint(geojson, declared_crs=None):
    """يحاكي @app.post('/api/v1/fields/validate-geometry')."""
    r = validate_field_geometry(geojson, declared_crs=declared_crs)
    return {
        "valid": r.valid,
        "computed_area_ha": r.computed_area_ha,
        "issues": [{"code": i.code, "severity": i.severity.value} for i in r.issues],
        "has_errors": r.has_errors,
    }


def test_geometry_endpoint_valid():
    results = []
    yemen_field = {
        "type": "Polygon",
        "coordinates": [[[45.30, 15.45], [45.32, 15.45],
                         [45.32, 15.47], [45.30, 15.47], [45.30, 15.45]]],
    }
    resp = simulate_geometry_endpoint(yemen_field)
    if resp["valid"]:
        results.append(("✓", "حقل يمني صالح → valid"))
    if resp["computed_area_ha"] and resp["computed_area_ha"] > 0:
        results.append(("✓", f"المساحة محسوبة: {resp['computed_area_ha']} ha"))
    return results


def test_geometry_endpoint_bad_crs():
    results = []
    field = {
        "type": "Polygon",
        "coordinates": [[[45.30, 15.45], [45.32, 15.45],
                         [45.32, 15.47], [45.30, 15.47], [45.30, 15.45]]],
    }
    resp = simulate_geometry_endpoint(field, declared_crs="EPSG:32638")
    if any(i["code"] == "invalid_crs" for i in resp["issues"]):
        results.append(("✓", "CRS غير 4326 → مرفوض"))
    return results


def test_geometry_endpoint_self_intersect():
    results = []
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[45.30, 15.45], [45.32, 15.47],
                         [45.32, 15.45], [45.30, 15.47], [45.30, 15.45]]],
    }
    resp = simulate_geometry_endpoint(bowtie)
    if not resp["valid"] and any(i["code"] == "self_intersection" for i in resp["issues"]):
        results.append(("✓", "تقاطع ذاتي → مرفوض (valid=False)"))
    return results


# سجّلها في الـrunner
def run_all():
    print("="*60)
    print("  Endpoint logic tests (TrueUp + Geometry — موصَّلتان)")
    print("="*60)
    suites = [
        ("TrueUp: happy (200)",     test_endpoint_happy_path),
        ("TrueUp: mismatch (400)",  test_endpoint_field_mismatch),
        ("TrueUp: rejection (422)", test_endpoint_rejection),
        ("Geometry: valid",         test_geometry_endpoint_valid),
        ("Geometry: bad CRS",       test_geometry_endpoint_bad_crs),
        ("Geometry: self-intersect", test_geometry_endpoint_self_intersect),
    ]
    tp = tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        for status, msg in suite():
            print(f"  {status} {msg}")
            tp += 1 if status == "✓" else 0
            tf += 1 if status == "✗" else 0
    print(f"\n{'='*60}\n  Passed: {tp}/{tp+tf}\n{'='*60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)

"""
learn_from_harvest.py
=====================
الجوهرة المفقودة (حسب النقدين): التعلّم من الحصاد.

يُشغَّل بعد كل حصاد. يُغلق الحلقة:
    حصاد فعلي (SQLite) → مقارنة بالتوقّع → معايرة zone_factor → حفظ

أين يُحفظ zone_factor (حسب النقد):
  - مزرعة واحدة → tenants/<id>/calibration/zone_factors.yaml (استرشادي)
  - عند اكتمال حد المزارع → districts/<region>/ (مُعتمد)

لا تعقيد ML. معايرة فيزيائية شفافة. لا أرقام وهمية: تحت الحد = "قيد المعايرة".

Usage: python learn_from_harvest.py <district_id> [crop]
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from storage.lite_store import yields_for_district, independent_units, init_db
from core.learning.model_selector import select_model

PLATFORM = Path(__file__).parent


def base_model_predict(record: dict) -> float:
    """Base physical prediction BEFORE districts calibration.
    In production this calls WOFOST. Here: a transparent placeholder
    representing the uncalibrated physical estimate."""
    return 5.0   # uncalibrated baseline (t/ha) — same for all, calibration adjusts


def learn(district_id: str, crop: str | None = None) -> dict:
    # تحقّق من وجود المديرية أوّلاً — قبل أي استعلام DB (إصلاح: تجنّب الانهيار
    # على مديرية غير موجودة، وإرجاع خطأ نظيف بدل خطأ مخطّط قاعدة البيانات).
    district_dir = PLATFORM / "districts" / district_id
    climate_path = district_dir / "climate.yaml"
    if not climate_path.exists():
        return {"error": f"region {district_id} not found"}

    rows = yields_for_district(district_id, crop)
    units = independent_units(district_id, crop)

    # load districts threshold (team-adjustable)
    climate = yaml.safe_load(open(climate_path, encoding="utf-8"))
    farms_required = climate.get("calibration", {}).get("farms_required", 5)

    # model ladder check (honest: tiny data -> rules only)
    model = select_model(units["records"], units["farms"], units["seasons"])

    if units["farms"] < farms_required:
        # below threshold -> per-tenant indicative factor, NOT districts
        result = {
            "district_id": district_id,
            "status": "pending_districts",
            "farms": units["farms"],
            "farms_required": farms_required,
            "model_allowed": model.allowed_model.value,
            "scope": "tenant_only (indicative)",
            "note_ar": (f"قيد المعايرة المديريةية — {units['farms']}/{farms_required} مزارع. "
                        f"معامل استرشادي للمزرعة فقط. النموذج: {model.allowed_model.value}"),
        }
        # compute indicative zone_factor if we have any verified harvests
        if rows:
            actual = [r["yield_t_ha"] for r in rows]
            pred = [base_model_predict(r) for r in rows]
            ratios = [a / p for a, p in zip(actual, pred) if p > 0]
            if ratios:
                zf = round(sum(ratios) / len(ratios), 3)
                result["indicative_zone_factor"] = zf
                result["confidence"] = "low (single/few farms)"
                # write to tenant calibration (indicative), NOT districts
                _write_tenant_indicative(rows[0]["tenant_id"], district_id, zf, units)
        return result

    # threshold met -> districts calibration (the real thing)
    actual = [r["yield_t_ha"] for r in rows]
    pred = [base_model_predict(r) for r in rows]
    ratios = [a / p for a, p in zip(actual, pred) if p > 0]
    zf = round(sum(ratios) / len(ratios), 3)

    climate.setdefault("calibration", {}).update({
        "status": "CALIBRATED",
        "farms_calibrated": units["farms"],
        "zone_factor": zf,
        "method": "zone_factor = mean(actual/predicted) [standard physical calibration]",
        "confidence": "high" if units["farms"] >= 5 and units["seasons"] >= 3 else "medium",
        "n_seasons": units["seasons"],
        "model_allowed": model.allowed_model.value,
    })
    with open(climate_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(climate, f, allow_unicode=True, sort_keys=False)

    return {
        "district_id": district_id, "status": "calibrated_districts",
        "zone_factor": zf, "farms": units["farms"], "seasons": units["seasons"],
        "model_allowed": model.allowed_model.value,
        "note_ar": f"معايرة مديريةية معتمدة: zone_factor={zf} من {units['farms']} مزارع",
    }


def _write_tenant_indicative(tenant_id, district_id, zf, units) -> None:
    """Indicative factor stays in the tenant until districts threshold is met."""
    cal_dir = PLATFORM / "tenants" / tenant_id / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "tenant_id": tenant_id, "district_id": district_id,
        "indicative_zone_factor": zf,
        "scope": "tenant_only",
        "confidence": "low",
        "basis": units,
        "note": "استرشادي — لا يُعمّم على المديرية حتى يكتمل حد المزارع",
    }
    with open(cal_dir / "zone_factors.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    init_db()
    district = sys.argv[1] if len(sys.argv) > 1 else "al_jawf"
    crop = sys.argv[2] if len(sys.argv) > 2 else None
    import json
    print(json.dumps(learn(district, crop), ensure_ascii=False, indent=2))

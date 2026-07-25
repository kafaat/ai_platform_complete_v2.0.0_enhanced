"""حارس بوّابة «مرجعيّ فقط» لكتالوج الأصناف (reference_only_not_operational).

كتالوج أصناف الحبوب (``api/food_grain_varieties.py``) موثّقٌ من المصدر لكنّه **محجوبٌ عن
التنفيذ الآليّ**: لا يجوز أن يستورده أيّ مسار قراريّ (crop_twin/المُجمِّع/جسر المرشّح/القرار
الموحّد/decision-service). أيّ استخدام لبيانات الأصناف في القرار يجب أن يمرّ عبر المسار
المحكوم (مرشّح → موافقة خبير)، لا حقناً مباشراً. هذا الحارس الساكن (نمط حارس حدّ الراستر)
يمنع انحدار البوّابة: يفشل إن استورد أيّ وحدة قراريّة الكتالوج.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLAT = ROOT / "services" / "sahool-platform" / "api"
DS = ROOT / "services" / "decision-service"

# الوحدات القراريّة التي يُمنَع أن تستورد كتالوج الأصناف (حجب التنفيذ الآليّ).
DECISION_MODULES = [
    PLAT / "routers" / "crop_twin.py",
    PLAT / "agronomic_context_composer.py",
    PLAT / "crop_decision_bridge.py",
    PLAT / "unified_decision.py",
    PLAT / "water_balance.py",
    PLAT / "irrigation_mpc.py",
]
FORBIDDEN = ("food_grain_varieties", "food_grain_variety")


def test_catalog_module_exists_and_declares_gate():
    src = (PLAT / "food_grain_varieties.py").read_text(encoding="utf-8")
    assert 'REFERENCE_ONLY_STATUS = "reference_only_not_operational"' in src
    # القارئ يفشل مُغلَقاً على خرق البوّابة (لا تقديم صامت).
    assert "VarietyCatalogIntegrityError" in src


def test_no_decision_module_imports_variety_catalog():
    offenders = []
    for mod in DECISION_MODULES:
        if not mod.exists():
            continue
        src = mod.read_text(encoding="utf-8")
        if any(tok in src for tok in FORBIDDEN):
            offenders.append(mod.relative_to(ROOT).as_posix())
    assert not offenders, (
        "خرق بوّابة reference_only: وحدة قراريّة تستورد كتالوج الأصناف "
        f"(يجب أن يمرّ عبر المسار المحكوم لا حقناً مباشراً): {offenders}"
    )


def test_decision_service_does_not_import_variety_catalog():
    if not DS.exists():
        pytest.skip("decision-service غير موجود")
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in DS.rglob("*.py")
        if "__pycache__" not in p.parts
        and any(tok in p.read_text(encoding="utf-8", errors="ignore") for tok in FORBIDDEN)
    ]
    assert not offenders, f"decision-service يستورد كتالوج الأصناف (محظور): {offenders}"

"""اختبار وحدة لقارئ الإجهاد المائيّ الكنسيّ (Bundle D / D2a) — اشتقاق صرف، بلا تصعيد.

يقفل المستويات المُقَرّة (المستخدم 2026-06-23): NORMAL (AWF>1−p) · WATCH (Dr≥RAW) ·
CRITICAL (AWF≤0.2). وصدق الغياب: لا استنزاف/TAW ⇒ None (لا كتلة مُلفّقة، لا قرار على غياب).
الكتلة موسومة calibrated=False (TAW/p غير معايَرين يمنيّاً).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.canonical_water_stress import WATER_STRESS_CRITICAL_AWF, canonical_water_stress
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def test_normal_when_well_watered():
    """استنزاف صغير نسبةً لـTAW ⇒ AWF عالٍ ⇒ normal."""
    # Dr=10, TAW=100 ⇒ AWF=0.9 > 1−p(=0.5) ⇒ normal
    w = canonical_water_stress({"depletion_mm": 10.0, "taw_mm": 100.0, "raw_fraction": 0.5})
    assert w is not None
    assert w["water_stress_awf"] == 0.9
    assert w["water_stress_class"] == "normal"
    assert w["calibrated"] is False
    assert w["source"] == "field_state.canonical"


def test_watch_when_depletion_reaches_raw():
    """Dr ≥ RAW لكن AWF > 0.2 ⇒ watch (تنبيه لا تصعيد)."""
    # Dr=60, TAW=100 ⇒ AWF=0.4 ؛ 1−p=0.5 ⇒ 0.2 < 0.4 ≤ 0.5 ⇒ watch
    w = canonical_water_stress({"depletion_mm": 60.0, "taw_mm": 100.0, "raw_fraction": 0.5})
    assert w is not None
    assert w["water_stress_awf"] == 0.4
    assert w["water_stress_class"] == "watch"


def test_critical_at_or_below_threshold():
    """AWF ≤ 0.2 (Dr ≥ 0.8·TAW) ⇒ critical (إجهاد ضارّ)."""
    # Dr=85, TAW=100 ⇒ AWF=0.15 ≤ 0.2 ⇒ critical
    w = canonical_water_stress(
        {"depletion_mm": 85.0, "taw_mm": 100.0, "raw_fraction": 0.5, "depletion_confidence": 0.9}
    )
    assert w is not None
    assert w["water_stress_awf"] == 0.15
    assert w["water_stress_class"] == "critical"
    assert w["depletion_confidence"] == 0.9
    # العتبة الحدّيّة بالضبط (AWF == 0.2) تُعدّ critical (≤).
    edge = canonical_water_stress({"depletion_mm": 80.0, "taw_mm": 100.0})
    assert edge["water_stress_awf"] == WATER_STRESS_CRITICAL_AWF
    assert edge["water_stress_class"] == "critical"


def test_default_raw_fraction_when_missing():
    """غياب raw_fraction ⇒ افتراضيّ 0.5 (لا رمي)."""
    w = canonical_water_stress({"depletion_mm": 30.0, "taw_mm": 100.0})
    assert w["raw_fraction"] == 0.5
    assert w["water_stress_class"] == "normal"  # AWF=0.7 > 0.5


def test_none_when_basis_missing_or_invalid():
    """غياب Dr أو TAW≤0 أو مدخل غير صالح ⇒ None (صدق + fail-safe)."""
    assert canonical_water_stress({"taw_mm": 100.0}) is None  # لا Dr
    assert canonical_water_stress({"depletion_mm": 50.0}) is None  # لا TAW
    assert canonical_water_stress({"depletion_mm": 50.0, "taw_mm": 0.0}) is None  # TAW≤0
    assert canonical_water_stress({"depletion_mm": "x", "taw_mm": 100.0}) is None  # Dr فاسد
    assert canonical_water_stress(None) is None
    assert canonical_water_stress("nope") is None


# ── D2b: التأكيد الطيفيّ + أهليّة التصعيد ──
# إجهاد طيفيّ شديد: NDMI=-0.1 (severe) + MSI=2.5 (severe) ⇒ fused severe ⇒ detected.
_CRIT = {"depletion_mm": 85.0, "taw_mm": 100.0, "depletion_confidence": 0.9}  # AWF=0.15 critical
# تاريخا اكتساب متوافقان (نفس اليوم) — سياسة التوافق الزمنيّ تسمح بالدمج.
_SAME_DATE = {"ndmi_date": "2026-07-05", "msi_date": "2026-07-05"}


def test_escalation_eligible_when_all_conditions_met():
    """critical ∧ conf≥0.8 ∧ مؤشّران متوافقان زمنيّاً ∧ إجهاد طيفيّ ⇒ eligible=True."""
    w = canonical_water_stress({**_CRIT, "ndmi": -0.1, "msi": 2.5, **_SAME_DATE})
    assert w["water_stress_class"] == "critical"
    assert w["spectral_confirmation_available"] is True
    assert w["spectral_temporal_compatible"] is True
    assert w["spectral_date_gap_days"] == 0
    assert w["spectral_stress_detected"] is True
    assert w["spectral_confidence"] == "high"  # كلاهما severe ⇒ اتّفاق
    assert w["escalation_eligible"] is True


def test_not_eligible_when_a_spectral_index_missing():
    """غياب أيّ مؤشّر ⇒ confirmation_available=False, detected=None, eligible=False (صدق)."""
    w = canonical_water_stress({**_CRIT, "ndmi": -0.1, **_SAME_DATE})  # لا msi
    assert w["spectral_confirmation_available"] is False
    assert w["spectral_stress_detected"] is None
    assert w["spectral_confidence"] is None
    assert w["escalation_eligible"] is False


def test_not_eligible_when_spectral_healthy():
    """مؤشّران لكن لا إجهاد طيفيّ (صحّيّ) ⇒ detected=False ⇒ eligible=False."""
    w = canonical_water_stress({**_CRIT, "ndmi": 0.5, "msi": 0.5, **_SAME_DATE})  # healthy
    assert w["spectral_confirmation_available"] is True
    assert w["spectral_stress_detected"] is False
    assert w["escalation_eligible"] is False


def test_not_eligible_when_low_depletion_confidence():
    """ثقة استنزاف < 0.8 ⇒ eligible=False (فيزياء غير موثوقة)."""
    w = canonical_water_stress(
        {**_CRIT, "depletion_confidence": 0.7, "ndmi": -0.1, "msi": 2.5, **_SAME_DATE}
    )
    assert w["escalation_eligible"] is False


def test_not_eligible_when_watch_not_critical():
    """watch (Dr≥RAW لكن AWF>0.2) + طيف شديد ⇒ eligible=False (ليس إجهاداً ضارّاً)."""
    # Dr=60, TAW=100 ⇒ AWF=0.4 watch
    w = canonical_water_stress(
        {
            "depletion_mm": 60.0,
            "taw_mm": 100.0,
            "depletion_confidence": 0.9,
            "ndmi": -0.1,
            "msi": 2.5,
            **_SAME_DATE,
        }
    )
    assert w["water_stress_class"] == "watch"
    assert w["escalation_eligible"] is False


# ── سياسة التوافق الزمنيّ لدمج NDMI+MSI (WS-D.3b) ──


def test_no_confirmation_when_dates_incompatible():
    """NDMI (5 يوليو) + MSI (20 يونيو) فجوة 15 يوماً > 12 ⇒ لا تأكيد (لا دمج زمنيّ خاطئ)."""
    w = canonical_water_stress(
        {**_CRIT, "ndmi": -0.1, "msi": 2.5, "ndmi_date": "2026-07-05", "msi_date": "2026-06-20"}
    )
    assert w["spectral_date_gap_days"] == 15
    assert w["spectral_temporal_compatible"] is False
    assert w["spectral_confirmation_available"] is False
    assert w["spectral_stress_detected"] is None
    assert w["escalation_eligible"] is False  # fail-closed رغم الإجهاد الشديد


def test_no_confirmation_when_a_date_missing():
    """غياب أحد التاريخين ⇒ لا يمكن التحقّق من التوافق ⇒ لا تأكيد (fail-closed)."""
    w = canonical_water_stress({**_CRIT, "ndmi": -0.1, "msi": 2.5, "ndmi_date": "2026-07-05"})
    assert w["spectral_date_gap_days"] is None
    assert w["spectral_temporal_compatible"] is False
    assert w["spectral_confirmation_available"] is False
    assert w["escalation_eligible"] is False


def test_confirmation_within_revisit_window():
    """فجوة ضمن النافذة (≤ 12 يوماً، مثلاً 3 أيّام) ⇒ دمج مسموح ⇒ تأكيد فعّال."""
    w = canonical_water_stress(
        {**_CRIT, "ndmi": -0.1, "msi": 2.5, "ndmi_date": "2026-07-05", "msi_date": "2026-07-08"}
    )
    assert w["spectral_date_gap_days"] == 3
    assert w["spectral_temporal_compatible"] is True
    assert w["spectral_confirmation_available"] is True
    assert w["escalation_eligible"] is True

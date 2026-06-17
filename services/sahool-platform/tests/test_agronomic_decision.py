"""اختبارات محرّك القرار الزراعيّ الموحّد (core.agronomic_decision) — الأولويّة 1.

نقيّة وحتميّة (لا I/O، لا خدمات) ⇒ مُعلَّمة `unit` لتُنفَّذ في بوّابة CI السريعة.
تثبّت العقد: الحجب بالحاجز، المرور دون تعارض، مصالحة الريّ↔الرشّ، قيد ميزانيّة الماء،
الترتيب بالإلحاح، أدنى ثقة، وقابليّة التسلسل (to_dict) وتطبيع الإلحاح.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.agronomic_decision import (  # noqa: E402
    DomainSignal,
    UnifiedDecision,
    Urgency,
    reconcile_decision,
    to_urgency,
)


# ── تطبيع الإلحاح ──
def test_to_urgency_normalizes_aliases():
    assert to_urgency("medium") is Urgency.MODERATE
    assert to_urgency("urgent") is Urgency.HIGH
    assert to_urgency("") is Urgency.NONE
    assert to_urgency(None) is Urgency.NONE
    assert to_urgency("HIGH") is Urgency.HIGH
    assert to_urgency(Urgency.CRITICAL) is Urgency.CRITICAL


def test_to_urgency_unknown_is_conservative_moderate():
    assert to_urgency("frobnicate") is Urgency.MODERATE


def test_urgency_rank_monotonic():
    ranks = [Urgency.NONE, Urgency.LOW, Urgency.MODERATE, Urgency.HIGH, Urgency.CRITICAL]
    assert [u.rank for u in ranks] == [0, 1, 2, 3, 4]


# ── الحجب بالحاجز (halt) ──
def test_halt_blocks_decision():
    sigs = [
        DomainSignal(domain="pest", action="spray", urgency=Urgency.HIGH),
        DomainSignal(domain="governance", action="none", halt=True, reason_ar="PHI لم يكتمل"),
    ]
    d = reconcile_decision("f1", sigs)
    assert d.state == "blocked"
    assert not d.is_ready
    assert d.action_plan == []
    assert "PHI لم يكتمل" in d.halt_reasons


def test_halt_collects_all_reasons():
    sigs = [
        DomainSignal(domain="salinity", action="none", halt=True, reason_ar="ملوحة حرجة"),
        DomainSignal(domain="governance", action="none", halt=True, reason_ar="حظر تنظيميّ"),
    ]
    d = reconcile_decision("f1", sigs)
    assert d.state == "blocked"
    assert set(d.halt_reasons) == {"ملوحة حرجة", "حظر تنظيميّ"}


# ── المرور دون تعارض ──
def test_quiet_signals_yield_ready_no_action():
    sigs = [DomainSignal(domain="weather", action="none")]
    d = reconcile_decision("f1", sigs)
    assert d.state == "ready"
    assert d.is_ready
    assert d.action_plan == []
    assert "لا إجراء" in d.rationale_ar


def test_empty_signals_yield_ready():
    d = reconcile_decision("f1", [])
    assert d.state == "ready"
    assert d.action_plan == []
    assert d.confidence == 1.0


def test_single_action_passthrough():
    sigs = [
        DomainSignal(
            domain="irrigation",
            action="irrigate",
            urgency=Urgency.HIGH,
            params={"water_mm": 20.0},
            reason_ar="رطوبة التربة منخفضة",
        )
    ]
    d = reconcile_decision("f1", sigs)
    assert d.state == "ready"
    assert len(d.action_plan) == 1
    a = d.action_plan[0]
    assert a.action == "irrigate"
    assert a.params["water_mm"] == 20.0
    assert d.reconciliations_ar == []


# ── مصالحة ١: الريّ ↔ الرشّ ──
def test_irrigation_deferred_for_spray_dry_window():
    sigs = [
        DomainSignal(
            domain="irrigation", action="irrigate", urgency=Urgency.HIGH, params={"water_mm": 20.0}
        ),
        DomainSignal(
            domain="pest",
            action="spray",
            urgency=Urgency.MODERATE,
            params={"needs_dry": True, "window_days": 3},
        ),
    ]
    d = reconcile_decision("f1", sigs)
    assert d.state == "ready"
    irr = next(a for a in d.action_plan if "irrig" in a.action)
    assert irr.action == "defer_irrigation"
    assert irr.params["defer_hours"] == 24  # min(48, max(24, 3*8=24)) = 24
    assert any("تعارض الريّ↔الرشّ" in r for r in d.reconciliations_ar)


def test_defer_hours_capped_at_48():
    sigs = [
        DomainSignal(domain="irrigation", action="irrigate", params={"water_mm": 10.0}),
        DomainSignal(domain="pest", action="spray", params={"needs_dry": True, "window_days": 10}),
    ]
    d = reconcile_decision("f1", sigs)
    irr = next(a for a in d.action_plan if "irrig" in a.action)
    assert irr.params["defer_hours"] == 48  # min(48, 80) = 48


def test_no_defer_when_spray_does_not_need_dry():
    sigs = [
        DomainSignal(domain="irrigation", action="irrigate", params={"water_mm": 10.0}),
        DomainSignal(domain="pest", action="spray", params={"needs_dry": False}),
    ]
    d = reconcile_decision("f1", sigs)
    irr = next(a for a in d.action_plan if "irrig" in a.action)
    assert irr.action == "irrigate"
    assert "defer_hours" not in irr.params
    assert d.reconciliations_ar == []


def test_no_defer_without_irrigation():
    sigs = [DomainSignal(domain="pest", action="spray", params={"needs_dry": True})]
    d = reconcile_decision("f1", sigs)
    assert all(a.action == "spray" for a in d.action_plan)
    assert d.reconciliations_ar == []


# ── مصالحة ٢: قيد ميزانيّة الماء ──
def test_water_budget_scales_irrigation():
    sigs = [
        DomainSignal(domain="irrigation", action="irrigate", params={"water_mm": 20.0}),
        DomainSignal(
            domain="economics",
            action="reduce_water",
            urgency=Urgency.LOW,
            params={"water_budget_pct": 88.0},
        ),
    ]
    d = reconcile_decision("f1", sigs)
    irr = next(a for a in d.action_plan if "irrig" in a.action)
    assert irr.params["water_mm"] == round(20.0 * 0.88, 1)  # 17.6
    assert any("ميزانيّة الماء" in r for r in d.reconciliations_ar)


def test_water_budget_full_no_scaling():
    sigs = [
        DomainSignal(domain="irrigation", action="irrigate", params={"water_mm": 20.0}),
        DomainSignal(domain="economics", action="reduce_water", params={"water_budget_pct": 100.0}),
    ]
    d = reconcile_decision("f1", sigs)
    irr = next(a for a in d.action_plan if "irrig" in a.action)
    assert irr.params["water_mm"] == 20.0
    assert all("ميزانيّة" not in r for r in d.reconciliations_ar)


def test_water_budget_and_defer_combine():
    sigs = [
        DomainSignal(domain="irrigation", action="irrigate", params={"water_mm": 20.0}),
        DomainSignal(domain="pest", action="spray", params={"needs_dry": True, "window_days": 3}),
        DomainSignal(domain="economics", action="reduce_water", params={"water_budget_pct": 50.0}),
    ]
    d = reconcile_decision("f1", sigs)
    irr = next(a for a in d.action_plan if "irrig" in a.action)
    assert irr.action == "defer_irrigation"
    assert irr.params["defer_hours"] == 24
    assert irr.params["water_mm"] == 10.0  # 20 * 0.5
    assert len(d.reconciliations_ar) == 2


# ── الترتيب بالإلحاح + الثقة ──
def test_plan_ordered_by_urgency_desc():
    sigs = [
        DomainSignal(domain="economics", action="reduce_water", urgency=Urgency.LOW),
        DomainSignal(
            domain="pest", action="spray", urgency=Urgency.CRITICAL, params={"needs_dry": False}
        ),
        DomainSignal(domain="soil", action="aerate", urgency=Urgency.MODERATE),
    ]
    d = reconcile_decision("f1", sigs)
    ranks = [a.urgency.rank for a in d.action_plan]
    assert ranks == sorted(ranks, reverse=True)
    assert d.action_plan[0].action == "spray"


def test_confidence_is_min_of_actionable():
    sigs = [
        DomainSignal(domain="irrigation", action="irrigate", confidence=0.9),
        DomainSignal(domain="pest", action="spray", confidence=0.6, params={"needs_dry": False}),
        DomainSignal(domain="weather", action="none", confidence=0.1),  # غير فاعل ⇒ يُتجاهَل
    ]
    d = reconcile_decision("f1", sigs)
    assert d.confidence == 0.6


def test_action_merges_domains_and_params():
    sigs = [
        DomainSignal(
            domain="soil", action="irrigate", urgency=Urgency.MODERATE, params={"water_mm": 15.0}
        ),
        DomainSignal(
            domain="weather", action="irrigate", urgency=Urgency.HIGH, params={"et0_mm": 6.0}
        ),
    ]
    d = reconcile_decision("f1", sigs)
    irr = d.action_plan[0]
    assert irr.action == "irrigate"
    assert set(irr.domains) == {"soil", "weather"}
    assert irr.urgency is Urgency.HIGH  # أعلى إلحاح بين الإشارتين
    assert irr.params["water_mm"] == 15.0
    assert irr.params["et0_mm"] == 6.0


# ── التسلسل (to_dict) ──
def test_to_dict_is_serializable():
    import json

    sigs = [
        DomainSignal(
            domain="irrigation", action="irrigate", urgency=Urgency.HIGH, params={"water_mm": 20.0}
        ),
        DomainSignal(
            domain="pest",
            action="spray",
            urgency=Urgency.MODERATE,
            params={"needs_dry": True, "window_days": 3},
        ),
        DomainSignal(domain="economics", action="reduce_water", params={"water_budget_pct": 80.0}),
    ]
    d = reconcile_decision("f1", sigs)
    blob = json.dumps(d.to_dict(), ensure_ascii=False)
    parsed = json.loads(blob)
    assert parsed["field_id"] == "f1"
    assert parsed["state"] == "ready"
    assert isinstance(parsed["action_plan"], list)
    assert all(isinstance(a["urgency"], str) for a in parsed["action_plan"])
    assert isinstance(parsed["confidence"], float)


def test_blocked_to_dict_serializable():
    import json

    d = reconcile_decision("f1", [DomainSignal(domain="gov", action="none", halt=True)])
    blob = json.dumps(d.to_dict(), ensure_ascii=False)
    assert json.loads(blob)["state"] == "blocked"


def test_unified_decision_is_ready_property():
    assert UnifiedDecision(field_id="f", state="ready").is_ready
    assert not UnifiedDecision(field_id="f", state="blocked").is_ready

"""اختبارات سجلّ سياسات القرار (core.policy_registry) — المرحلة B، الشريحة 5.

نقيّة وحتميّة ⇒ `unit`. تثبّت: مطابقة النطاق (بدل/تطابق/تعطيل)، الدمج التحفّظيّ للأثر
(auto_block غالب، أقصى موافقات، أدنى سقف ماء)، الترتيب بالأولويّة، وأثر التدقيق.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.policy_registry import (  # noqa: E402
    Policy,
    policy_matches,
    resolve_policies,
)


# ── مطابقة النطاق ──
def test_wildcard_scope_matches_everything():
    p = Policy(policy_id="p1", name="عامّة", scope={})
    assert policy_matches(p, {"action_type": "irrigation", "risk_level": "LOW"})
    assert policy_matches(p, {})


def test_scope_field_must_match():
    p = Policy(policy_id="p1", name="رشّ", scope={"action_type": "spray"})
    assert policy_matches(p, {"action_type": "spray"})
    assert not policy_matches(p, {"action_type": "irrigation"})
    # حقل ناقص في السياق ⇒ لا يطابق نطاقاً مُحدَّداً
    assert not policy_matches(p, {})


def test_scope_match_is_case_insensitive():
    p = Policy(policy_id="p1", name="حرِج", scope={"risk_level": "high"})
    assert policy_matches(p, {"risk_level": "HIGH"})


def test_multi_field_scope_all_must_match():
    p = Policy(policy_id="p1", name="رشّ تمر", scope={"action_type": "spray", "crop": "dates"})
    assert policy_matches(p, {"action_type": "spray", "crop": "dates"})
    assert not policy_matches(p, {"action_type": "spray", "crop": "wheat"})


def test_disabled_policy_never_matches():
    p = Policy(policy_id="p1", name="معطّلة", scope={}, enabled=False)
    assert not policy_matches(p, {"action_type": "spray"})


# ── دمج الأثر ──
def test_resolve_no_match_is_empty():
    pols = [
        Policy(
            policy_id="p1", name="رشّ", scope={"action_type": "spray"}, effect={"auto_block": True}
        )
    ]
    r = resolve_policies(pols, {"action_type": "irrigation"})
    assert r.auto_block is False
    assert r.applied_policy_ids == []


def test_auto_block_dominates():
    pols = [
        Policy(
            policy_id="p1",
            name="احجب الرشّ",
            scope={"action_type": "spray"},
            effect={"auto_block": True},
        ),
    ]
    r = resolve_policies(pols, {"action_type": "spray"})
    assert r.auto_block is True
    assert "p1" in r.applied_policy_ids
    assert any("p1" in pid for pid in r.applied_policy_ids)
    assert r.reasons_ar


def test_require_approvals_takes_max():
    pols = [
        Policy(policy_id="p1", name="موافقتان", scope={}, effect={"require_approvals": 2}),
        Policy(policy_id="p2", name="ثلاث", scope={}, effect={"require_approvals": 3}),
    ]
    r = resolve_policies(pols, {"action_type": "spray"})
    assert r.require_approvals == 3  # الأقصى (تحفّظ)
    assert set(r.applied_policy_ids) == {"p1", "p2"}


def test_water_cap_takes_min():
    pols = [
        Policy(policy_id="p1", name="سقف ٩٠", scope={}, effect={"water_cap_pct": 90.0}),
        Policy(policy_id="p2", name="سقف ٧٠", scope={}, effect={"water_cap_pct": 70.0}),
    ]
    r = resolve_policies(pols, {"action_type": "irrigation"})
    assert r.water_cap_pct == 70.0  # الأدنى (أقسى سقف)


def test_priority_ordering_in_applied_ids():
    pols = [
        Policy(policy_id="low", name="منخفضة", scope={}, effect={"auto_block": True}, priority=1),
        Policy(policy_id="high", name="عالية", scope={}, effect={"auto_block": True}, priority=9),
    ]
    r = resolve_policies(pols, {"action_type": "spray"})
    # الأعلى أولويّة يُطبَّق أوّلاً (يظهر أوّلاً في الأثر)
    assert r.applied_policy_ids[0] == "high"


def test_policy_with_no_effect_not_recorded():
    # سياسة تطابق لكن أثرها فارغ ⇒ لا تُسجَّل (لا حوكمة وهميّة)
    pols = [Policy(policy_id="p1", name="بلا أثر", scope={}, effect={})]
    r = resolve_policies(pols, {"action_type": "spray"})
    assert r.applied_policy_ids == []


def test_resolved_to_dict_serializable():
    import json

    pols = [Policy(policy_id="p1", name="x", scope={}, effect={"water_cap_pct": 80.0})]
    r = resolve_policies(pols, {"action_type": "irrigation"})
    blob = json.dumps(r.to_dict(), ensure_ascii=False)
    assert json.loads(blob)["water_cap_pct"] == 80.0

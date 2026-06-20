"""اختبار منطق إزالة التكرار العنقوديّ للـactuator (PR #393) — الجزء النقيّ + حارس الهجرة.

نمط الإغلاق المرن (local→shadow→cluster): يُختبَر دمج القرار حتميّاً بلا قاعدة؛ الفحص
العنقوديّ الذرّيّ نفسه تكامليّ (يتطلّب Postgres). + حارس بنية جدول المخزن العنقوديّ.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

from shared.actuator_idempotency import (  # noqa: E402
    METRIC_CLUSTER_HIT,
    METRIC_CLUSTER_UNAVAILABLE,
    METRIC_DUPLICATE_BLOCKED,
    METRIC_LOCAL_HIT,
    METRIC_SHADOW_DIVERGENCE,
    decide_fire,
    idempotency_counters,
    resolve_idempotency_mode,
)

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── تطبيع الوضع ──
def test_mode_defaults_to_local():
    """أيّ قيمة مجهولة/غائبة ⇒ local (الأكثر تحفّظاً، السلوك الحاليّ)."""
    for raw in (None, "", "  ", "redis", "REQUIRED", "xyz"):
        assert resolve_idempotency_mode(raw) == "local"


def test_mode_known_values_case_insensitive():
    assert resolve_idempotency_mode("shadow") == "shadow"
    assert resolve_idempotency_mode(" Cluster ") == "cluster"
    assert resolve_idempotency_mode("LOCAL") == "local"


# ── دمج القرار: local ──
def test_local_mode_uses_local_decision():
    assert decide_fire("local", True, False, True) == (True, "local")
    assert decide_fire("local", False, True, True) == (False, "local")


# ── دمج القرار: cluster (العنقوديّ يحسم، fail-soft) ──
def test_cluster_mode_authoritative_when_available():
    assert decide_fire("cluster", True, True, True) == (True, "cluster_fire")
    # العنقوديّ يمنع تكراراً فاتَ المحلّيّ (المحلّيّ يقول أطلِق، العنقوديّ يقول لا) ⇒ لا إطلاق.
    assert decide_fire("cluster", True, False, True) == (False, "cluster_skip")


def test_cluster_mode_fail_soft_to_local_when_store_down():
    """تعذّر المخزن ⇒ رجوع للقرار المحلّيّ (لا نوقف الفعل الميدانيّ كلّيّاً)."""
    assert decide_fire("cluster", True, False, False) == (True, "cluster_unavailable_fallback")
    assert decide_fire("cluster", False, False, False) == (False, "cluster_unavailable_fallback")


# ── دمج القرار: shadow (المحلّيّ يحسم، نرصد التباين) ──
def test_shadow_mode_local_decides_but_records_divergence():
    # اتّفاق ⇒ shadow_agree، والقرار محلّيّ.
    assert decide_fire("shadow", True, True, True) == (True, "shadow_agree")
    # تباين (العنقوديّ كان سيمنع) ⇒ يُرصَد لكنّ المحلّيّ يقرّر (مرحلة مراقبة آمنة).
    assert decide_fire("shadow", True, False, True) == (True, "shadow_divergence")


def test_shadow_mode_store_unavailable():
    assert decide_fire("shadow", True, False, False) == (True, "shadow_store_unavailable")


# ── العدّادات المعتمدة (شروط القبول) ──
def test_local_mode_zero_cluster_metrics():
    """شرط 1: local لا يلمس أيّ عدّاد عنقوديّ (صفر-تأثير على السلوك القائم)."""
    # إطلاق عاديّ (لا تكرار) ⇒ لا عدّادات إطلاقاً.
    assert idempotency_counters("local", True, False, False, True) == ()
    # تكرار محلّيّ ⇒ local_hit + duplicate_blocked فقط (لا عدّاد عنقوديّ).
    c = idempotency_counters("local", False, False, False, False)
    assert METRIC_LOCAL_HIT in c and METRIC_DUPLICATE_BLOCKED in c
    assert METRIC_CLUSTER_HIT not in c and METRIC_SHADOW_DIVERGENCE not in c
    assert METRIC_CLUSTER_UNAVAILABLE not in c


def test_shadow_records_divergence_and_does_not_change_decision():
    """شرط 2: shadow يقيس فقط — القرار يبقى محلّيّاً، ويُرصَد التباين (معيار الانتقال)."""
    # المحلّيّ يطلق، العنقوديّ كان سيمنع ⇒ تباين مُسجَّل، والقرار محلّيّ (fire=True ⇒ لا منع).
    c = idempotency_counters(
        "shadow", local_fire=True, cluster_fire=False, cluster_available=True, fire=True
    )
    assert METRIC_SHADOW_DIVERGENCE in c
    assert METRIC_CLUSTER_HIT in c  # العنقوديّ التقط تكراراً
    assert METRIC_DUPLICATE_BLOCKED not in c  # لكنّ shadow لم يمنع (قياس فقط)


def test_shadow_no_divergence_when_agree():
    """اتّفاق shadow ⇒ لا تباين (الهدف: صفر تباين قبل تفعيل cluster)."""
    c = idempotency_counters("shadow", True, True, True, True)
    assert METRIC_SHADOW_DIVERGENCE not in c


def test_cluster_blocks_duplicate():
    """شرط 3: cluster يمنع التكرار (العنقوديّ يحسم) ⇒ duplicate_blocked + cluster_hit."""
    c = idempotency_counters(
        "cluster", local_fire=True, cluster_fire=False, cluster_available=True, fire=False
    )
    assert METRIC_CLUSTER_HIT in c
    assert METRIC_DUPLICATE_BLOCKED in c


def test_cluster_unavailable_records_and_falls_back():
    """شرط 4: تعذّر المخزن في cluster ⇒ يُسجَّل cluster_unavailable + رجوع محلّيّ (لا crash)."""
    # المخزن غير متاح، المحلّيّ يطلق ⇒ fire=True (رجوع)، عدّاد unavailable مرفوع، لا منع.
    c = idempotency_counters(
        "cluster", local_fire=True, cluster_fire=False, cluster_available=False, fire=True
    )
    assert METRIC_CLUSTER_UNAVAILABLE in c
    assert METRIC_DUPLICATE_BLOCKED not in c
    assert METRIC_CLUSTER_HIT not in c  # غير متاح ⇒ لا ضربة عنقوديّة


# ── حارس الهجرة v81 ──
def test_v81_actuator_dedup_table_and_rls():
    sql = _read("migrations/v81_actuator_command_dedup.sql")
    assert "CREATE TABLE IF NOT EXISTS actuator_command_dedup" in sql
    assert "dedup_key       TEXT         PRIMARY KEY" in sql
    assert "tenant_id       UUID         NOT NULL" in sql
    # عزل المستأجِر الصريح (يطابق sahool_inspector/test_rls).
    assert "ALTER TABLE actuator_command_dedup ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE actuator_command_dedup FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation ON actuator_command_dedup" in sql
    assert "current_setting('app.current_tenant', true)" in sql

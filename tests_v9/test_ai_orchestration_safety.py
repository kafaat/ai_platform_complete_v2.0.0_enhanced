"""حُرّاس سلامة تنسيق طبقات الذكاء (supervisor-agent ↔ guardrails-engine).

فحص عميق للمحور D (AI Architecture & Agent Orchestration). التحقّق المباشر أظهر أنّ مسار
الحَوكمة **سليم ومحكم**: لا توصية قابلة للتنفيذ تتجاوز Guardrails /validate، والتعذّر
fail-safe (لا fail-open)، وطبقة الكيمياء fail-closed على المجهول. هذه الحُرّاس تُثبّت تلك
الضمانات كبوّابة CI (نفس فلسفة حارسي RLS/الأحداث) كي لا ينحدر أحدها صامتاً.

(A) حُرّاس مصدر — لا تجاوز للبوّابة + fail-safe عند تعذّرها (تُنفَّذ في CI بلا خدمات).
(B) سلوكيّ — ChemicalSafetyTier fail-closed (يتخطّى إن غابت تبعيّات الخدمة).

ملاحظة معماريّة (لا تُغيَّر هنا): يوجد نظاما حَوكمة — guardrails-engine (طبقات كيمياء/
اقتصاد/بيئة لتوصيات الوكيل) وplatform core.guardrails (PHI/ملوحة HALT لتنفيذ الموزِّع).
هما طبقتان مكمّلتان لكن تغطيتهما للقواعد تختلف (الأولى بلا PHI، الثانية بلا مواد محظورة/
جرعات) ⇒ خطر انجراف على المدى الطويل. التوحيد قرار معماريّ (لا إصلاح جراحيّ) — مُوثَّق للقرار.
"""

from __future__ import annotations

import os

import pytest
from supervisor_route_source import supervisor_combined_source

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")
AGENT = os.path.join(ROOT, "services/supervisor-agent")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _supervisor_src() -> str:
    """مصدر supervisor المُسلسَل (main.py + routers/*.py) بعد التفكيك المحفوظ-السلوك.

    مُعالِجات ``/agent/*`` انتقلت إلى ``routers/agent.py``؛ الحُرّاس الساكنة يجب أن
    تمسح الوحدتين معاً كي يبقى التأكيد الأمنيّ صحيحاً (لا إضعاف، فقط توسيع النطاق).
    """
    return supervisor_combined_source(ROOT)


# ── (A) لا تجاوز للبوّابة (no recommendation→command bypass) ──
def test_query_path_validates_actionable_via_guardrails():
    src = _supervisor_src()
    assert "_validate_actions_via_guardrails(" in src, "مسار /agent/query لا يمرّر الإجراءات للبوّابة"
    # الحَوكمة مشروطة بوجود إجراءات قابلة للتنفيذ
    assert 'result.get("actionable")' in src or 'result.get("actions"' in src, (
        "لا يكتشف الإجراءات القابلة للتنفيذ"
    )


def test_optimize_path_validates_recommendation():
    src = _supervisor_src()
    assert "_validate_via_guardrails(" in src, "مسار /agent/optimize لا يمرّر التوصية للبوّابة"


def test_guardrails_validate_called_with_service_token():
    src = _supervisor_src()
    assert "/validate" in src, "لا يستدعي نقطة الحَوكمة /validate"
    assert "X-Agent-Token" in src, "استدعاء البوّابة بلا توكن خدمة"


# ── (A) fail-safe عند تعذّر البوّابة (لا fail-open) ──
def test_guardrails_unavailable_is_fail_safe():
    src = _supervisor_src()
    # عند التعذّر: allowed ليس True، وحالة «استشاريّة بانتظار التحقّق» + لا تنفيذ تلقائيّ
    assert "guardrails-unavailable" in src, "لا معالجة صريحة لتعذّر البوّابة"
    assert "advisory_pending_validation" in src, "لا وسم استشاريّ عند التعذّر"
    assert "لا تُنفَّذ تلقائيّاً" in src, "لا تأكيد على عدم التنفيذ التلقائيّ عند التعذّر"
    # لا fail-open: لا يُسند allowed=True في فرع التعذّر
    fallback = src[src.index("guardrails-unavailable") - 400 : src.index("guardrails-unavailable")]
    assert '"allowed": True' not in fallback, "fail-open: البوّابة المتعذّرة تسمح بالتنفيذ!"


# ── (A) الحَوكمة في guardrails-engine محروسة بتوكن خدمة ──
def test_guardrails_engine_validate_requires_service_token():
    src = _read("services/guardrails-engine/main.py")
    assert "_require_service_token" in src, "نقطة /validate في guardrails-engine بلا توكن خدمة"


# ── (B) ChemicalSafetyTier fail-closed (سلوكيّ) ──
@pytest.fixture(scope="module")
def chem():
    import importlib.util
    import sys

    if AGENT not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "services/guardrails-engine"))
    path = os.path.join(ROOT, "services/guardrails-engine/tiers/chemical_tier.py")
    spec = importlib.util.spec_from_file_location("chemical_tier_test", path)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except Exception:  # noqa: BLE001
        pytest.skip("تعذّر استيراد ChemicalSafetyTier")
    return m.ChemicalSafetyTier()


async def test_banned_chemical_blocked(chem):
    r = await chem.validate("pesticide", {"chemical": "DDT", "dosage_kg_ha": 0.1}, {})
    assert r["passed"] is False
    assert any(f["rule"] == "banned_substance" for f in r["findings"])


async def test_unknown_chemical_fail_closed(chem):
    # مادة مجهولة ⇒ تُحجب (fail-closed، تتطلّب مراجعة خبير) — لا تمرير صامت
    r = await chem.validate("pesticide", {"chemical": "zzz_unknown", "dosage_kg_ha": 0.1}, {})
    assert r["passed"] is False
    assert any(f["rule"] == "unknown_chemical" for f in r["findings"])


async def test_overdose_blocked(chem):
    r = await chem.validate(
        "pesticide", {"chemical": "glyphosate", "dosage_kg_ha": 99.0, "crop": "wheat"}, {}
    )
    assert r["passed"] is False
    assert any(f["rule"] == "max_dosage_exceeded" for f in r["findings"])


async def test_safe_application_passes(chem):
    # mancozeb (غير محظور/مقيّد) بجرعة دون الحدّ المخصّص للمحصول ⇒ يمرّ
    r = await chem.validate(
        "pesticide", {"chemical": "mancozeb", "dosage_kg_ha": 1.0, "crop": "potato"}, {}
    )
    assert r["passed"] is True

"""Unit/security tests: إلزاميّة إدامة القرار القابل للتنفيذ + فحص ملكيّة الحقل (Stage A P0).

الفجوة المُثبَتة (تدقيق المعماريّة): `persist_decision_if_enabled` كانت تُدِيم القرار فقط
إذا رُفِع علم SAHOOL_AUTO_PERSIST_DECISIONS — فقد يُتصرَّف بقرارٍ **قابل للتنفيذ** (أقرّت
حوكمته التوزيع) بلا سجلّ دائم. كما لم يكن ثمّ فحص ملكيّة/مستأجِر قبل الإدراج — فقد يُكتَب
قرار على حقلٍ لا يملكه المنادي.

الخطّ الأحمر المُثبَّت هنا (صدق + أمان، fail-closed):
  (أ) قرار قابل للتنفيذ يُدام **رغم إطفاء العلم** (إلزاميّ).
  (ب) قرار استشاريّ يبقى محكوماً بالعلم (مُطفأ ⇒ لا إدامة).
  (ج) عدم تطابق المستأجِر ⇒ يُرفَض (403).
  (د) OwnerLookupUnavailable ⇒ 503 (fail-closed).
  (هـ) بلا DATABASE_URL (DB-less/CI) ⇒ لا حجب (تُبقى خضرة CI).

P4.7 direct-DB final sweep: الإدامة لم تعد INSERT مباشراً بل تفويض عبر واجهة
decision-service. نقيّ بلا قاعدة: نُرقِّع دالّة الواجهة كما تُستورَد في الموجِّه
(``_record_decision_via_service``) ونُرقِّع مصدر الملكيّة — نتحقّق أنّ المنصّة تحفظ فحص
الملكيّة/الإلزاميّة/الإغلاق المرن وتُفوّض الكتابة للمالك (decision-service).
"""

from __future__ import annotations

import os
import sys

import pytest

# تبعيّات الخدمة (fastapi…) غير مثبّتة في بيئة الوحدات بـCI ⇒ تخطٍّ على مستوى الوحدة
# (لا خطأ تجميع يُقاطع الجلسة كلّها)، مطابقةً لبقيّة اختبارات الخدمة في tests_v9.
pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import api.main  # noqa: F401,E402 — تهيئة api.main قبل استيراد الموجِّه
import api.routers.decision_record as dr  # noqa: E402
from core.canonical_schemas import UserRole, UserSchema  # noqa: E402

_TENANT = "00000000-0000-0000-0000-000000000007"
_OTHER_TENANT = "00000000-0000-0000-0000-000000000099"

_USER = UserSchema(
    user_id="u-mand",
    tenant_id=_TENANT,
    role=UserRole.OWNER,
    name_ar="إلزاميّة",
)

_EXECUTABLE_DECISION = {
    "decision_id": "dec_exec",
    "actionable": True,
    "governance": {"status": "approved"},
}
_ADVISORY_DECISION = {
    "decision_id": "dec_adv",
    "actionable": True,
    "governance": {"status": "not_evaluated"},
}


@pytest.fixture
def captured_inserts(monkeypatch):
    """يلتقط تفويض الإدامة إلى decision-service عبر ترقيع دالّة الواجهة في الموجِّه.

    كلّ عنصر في المُسجِّل هو حمولة القرار المُمرَّرة إلى ``_record_decision_via_service``.
    فحص الملكيّة يسبق التفويض؛ رفض الملكيّة ⇒ لا استدعاء ⇒ مُسجِّل فارغ (كالإدراج سابقاً).
    """
    recorder: list = []

    async def _fake_record(payload, *, tenant_id=None):
        recorder.append(payload)
        return {
            "persisted": True,
            "decision_id": payload.get("decision_id"),
            "tenant_id": tenant_id,
        }

    monkeypatch.setattr(dr, "_record_decision_via_service", _fake_record)
    return recorder


# ── (أ) القرار القابل للتنفيذ يُدام رغم إطفاء العلم ──────────────────────────
@pytest.mark.unit
async def test_executable_persists_even_when_flag_off(captured_inserts, monkeypatch):
    monkeypatch.delenv("SAHOOL_AUTO_PERSIST_DECISIONS", raising=False)
    # بلا DATABASE_URL ⇒ فحص الملكيّة لا يحجب (CI)؛ الإدامة تبقى إلزاميّة.
    monkeypatch.setattr(dr, "DATABASE_URL", "")

    ok = await dr.persist_decision_if_enabled(
        _USER,
        decision_id="dec_exec",
        decision_type="field_intelligence",
        decision_value=_EXECUTABLE_DECISION,
        field_id="F-EXEC-1",
    )
    assert ok is True
    assert len(captured_inserts) == 1  # أُدِيم فعلاً رغم العلم المُطفأ


@pytest.mark.unit
async def test_executable_via_explicit_param_persists(captured_inserts, monkeypatch):
    """تمرير executable=True صراحةً يفرض الإدامة الإلزاميّة أيّاً كان شكل decision_value."""
    monkeypatch.delenv("SAHOOL_AUTO_PERSIST_DECISIONS", raising=False)
    monkeypatch.setattr(dr, "DATABASE_URL", "")

    ok = await dr.persist_decision_if_enabled(
        _USER,
        decision_id="dec_x",
        decision_type="crop_twin",
        decision_value={"any": "shape"},
        field_id=None,
        executable=True,
    )
    assert ok is True
    assert len(captured_inserts) == 1


@pytest.mark.unit
async def test_executable_persist_failure_fails_closed(captured_inserts, monkeypatch):
    """فشل إدامة قرار قابل للتنفيذ ⇒ 503 (fail-closed، لا يُمضى كأنّه سُجِّل)."""
    monkeypatch.delenv("SAHOOL_AUTO_PERSIST_DECISIONS", raising=False)
    monkeypatch.setattr(dr, "DATABASE_URL", "")

    async def _boom(payload, *, tenant_id=None):
        raise RuntimeError("decision-service down")

    monkeypatch.setattr(dr, "_record_decision_via_service", _boom)

    with pytest.raises(HTTPException) as exc:
        await dr.persist_decision_if_enabled(
            _USER,
            decision_id="dec_exec",
            decision_type="field_intelligence",
            decision_value=_EXECUTABLE_DECISION,
            field_id=None,
            executable=True,
        )
    assert exc.value.status_code == 503


# ── (ب) القرار الاستشاريّ يبقى محكوماً بالعلم ────────────────────────────────
@pytest.mark.unit
async def test_advisory_gated_by_flag_off(captured_inserts, monkeypatch):
    monkeypatch.delenv("SAHOOL_AUTO_PERSIST_DECISIONS", raising=False)
    monkeypatch.setattr(dr, "DATABASE_URL", "")

    ok = await dr.persist_decision_if_enabled(
        _USER,
        decision_id="dec_adv",
        decision_type="crop_twin",
        decision_value=_ADVISORY_DECISION,
        field_id="F-ADV-1",
    )
    assert ok is False
    assert captured_inserts == []  # لا مسّ بالقاعدة عند الإطفاء (best-effort)


@pytest.mark.unit
async def test_advisory_persists_when_flag_on(captured_inserts, monkeypatch):
    monkeypatch.setenv("SAHOOL_AUTO_PERSIST_DECISIONS", "1")
    monkeypatch.setattr(dr, "DATABASE_URL", "")

    ok = await dr.persist_decision_if_enabled(
        _USER,
        decision_id="dec_adv",
        decision_type="crop_twin",
        decision_value=_ADVISORY_DECISION,
        field_id=None,
    )
    assert ok is True
    assert len(captured_inserts) == 1


@pytest.mark.unit
async def test_advisory_persist_failure_is_best_effort(monkeypatch):
    """فشل إدامة قرار استشاريّ (العلم مرفوع) ⇒ False بلا رمي (لا يكسر إصدار القرار)."""
    monkeypatch.setenv("SAHOOL_AUTO_PERSIST_DECISIONS", "1")
    monkeypatch.setattr(dr, "DATABASE_URL", "")

    async def _boom(payload, *, tenant_id=None):
        raise RuntimeError("decision-service down")

    monkeypatch.setattr(dr, "_record_decision_via_service", _boom)

    ok = await dr.persist_decision_if_enabled(
        _USER,
        decision_id="dec_adv",
        decision_type="crop_twin",
        decision_value=_ADVISORY_DECISION,
        field_id=None,
    )
    assert ok is False


# ── (ج) عدم تطابق المستأجِر ⇒ 403 ────────────────────────────────────────────
@pytest.mark.security
async def test_tenant_mismatch_denied(captured_inserts, monkeypatch):
    """الحقل مملوك لمستأجِر آخر ⇒ 403، ولا إدراج إطلاقاً (حتى لقرار قابل للتنفيذ)."""
    monkeypatch.delenv("SAHOOL_AUTO_PERSIST_DECISIONS", raising=False)
    monkeypatch.setattr(dr, "DATABASE_URL", "postgresql://x")  # قاعدة مُهيّأة

    async def _owner(_field_id):
        return _OTHER_TENANT  # مالك مختلف عن مستأجِر المنادي

    monkeypatch.setattr(dr, "_field_owner_tenant", _owner)

    with pytest.raises(HTTPException) as exc:
        await dr.persist_decision_if_enabled(
            _USER,
            decision_id="dec_exec",
            decision_type="field_intelligence",
            decision_value=_EXECUTABLE_DECISION,
            field_id="F-OTHER",
            executable=True,
        )
    assert exc.value.status_code == 403
    assert captured_inserts == []  # لم يُكتَب شيء على حقل الغير


@pytest.mark.security
async def test_field_not_found_denied(captured_inserts, monkeypatch):
    """الحقل غير موجود رغم القاعدة المُهيّأة ⇒ 404، لا إدراج."""
    monkeypatch.setattr(dr, "DATABASE_URL", "postgresql://x")

    async def _owner(_field_id):
        return None  # استعلام نجح بلا صفّ ⇒ حقل غير موجود

    monkeypatch.setattr(dr, "_field_owner_tenant", _owner)

    with pytest.raises(HTTPException) as exc:
        await dr.persist_decision_if_enabled(
            _USER,
            decision_id="dec_exec",
            decision_type="field_intelligence",
            decision_value=_EXECUTABLE_DECISION,
            field_id="F-GHOST",
            executable=True,
        )
    assert exc.value.status_code == 404
    assert captured_inserts == []


@pytest.mark.security
async def test_owner_match_allows_persist(captured_inserts, monkeypatch):
    """المالك = مستأجِر المنادي ⇒ يُسمح بالإدامة."""
    monkeypatch.setattr(dr, "DATABASE_URL", "postgresql://x")

    async def _owner(_field_id):
        return _TENANT  # نفس مستأجِر المنادي

    monkeypatch.setattr(dr, "_field_owner_tenant", _owner)

    ok = await dr.persist_decision_if_enabled(
        _USER,
        decision_id="dec_exec",
        decision_type="field_intelligence",
        decision_value=_EXECUTABLE_DECISION,
        field_id="F-MINE",
        executable=True,
    )
    assert ok is True
    assert len(captured_inserts) == 1


# ── (د) تعذّر إثبات الملكيّة ⇒ 503 (fail-closed) ─────────────────────────────
@pytest.mark.security
async def test_owner_lookup_unavailable_returns_503(captured_inserts, monkeypatch):
    monkeypatch.setattr(dr, "DATABASE_URL", "postgresql://x")

    async def _owner(_field_id):
        raise dr.OwnerLookupUnavailable("connect failed")

    monkeypatch.setattr(dr, "_field_owner_tenant", _owner)

    with pytest.raises(HTTPException) as exc:
        await dr.persist_decision_if_enabled(
            _USER,
            decision_id="dec_exec",
            decision_type="field_intelligence",
            decision_value=_EXECUTABLE_DECISION,
            field_id="F-UNREACHABLE",
            executable=True,
        )
    assert exc.value.status_code == 503
    assert captured_inserts == []  # تعذّر الإثبات ⇒ لا كتابة على غموض


# ── (هـ) بلا DATABASE_URL (DB-less/CI) ⇒ لا حجب ─────────────────────────────
@pytest.mark.unit
async def test_db_less_does_not_block_ownership(captured_inserts, monkeypatch):
    """بلا DATABASE_URL: _field_owner_tenant يعيد None ⇒ لا حجب — تُبقى خضرة CI."""
    monkeypatch.setattr(dr, "DATABASE_URL", "")

    owner = await dr._field_owner_tenant("F-ANY")
    assert owner is None  # وضع بلا قاعدة مقصود

    # قرار قابل للتنفيذ على حقلٍ، بلا قاعدة ⇒ يُدام دون حجب ملكيّة.
    ok = await dr.persist_decision_if_enabled(
        _USER,
        decision_id="dec_exec",
        decision_type="field_intelligence",
        decision_value=_EXECUTABLE_DECISION,
        field_id="F-DBLESS",
        executable=True,
    )
    assert ok is True
    assert len(captured_inserts) == 1


# ── منطق استنباط القابليّة للتنفيذ (نقيّ) ────────────────────────────────────
@pytest.mark.unit
def test_executable_derivation_pure():
    assert (
        dr._decision_is_executable({"actionable": True, "governance": {"status": "approved"}}, None)
        is True
    )
    assert (
        dr._decision_is_executable({"actionable": True, "governance": {"status": "passed"}}, None)
        is True
    )
    # actionable لكن الحوكمة غير مُقَرّة ⇒ ليس قابلاً للتنفيذ.
    assert (
        dr._decision_is_executable(
            {"actionable": True, "governance": {"status": "not_evaluated"}}, None
        )
        is False
    )
    assert (
        dr._decision_is_executable({"actionable": True, "governance": {"status": "error"}}, None)
        is False
    )
    # actionable بلا حوكمة ⇒ ليس قابلاً للتنفيذ (fail-closed).
    assert dr._decision_is_executable({"actionable": True}, None) is False
    # مفتاح executable صريح يُحترَم.
    assert dr._decision_is_executable({"executable": True}, None) is True
    assert (
        dr._decision_is_executable(
            {"executable": False, "actionable": True, "governance": {"status": "approved"}}, None
        )
        is False
    )
    # تمرير صريح يَسبق الاستنباط.
    assert dr._decision_is_executable({"governance": {"status": "not_evaluated"}}, True) is True
    assert (
        dr._decision_is_executable(
            {"governance": {"status": "approved"}, "actionable": True}, False
        )
        is False
    )

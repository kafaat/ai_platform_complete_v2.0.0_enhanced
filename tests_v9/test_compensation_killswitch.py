"""التعويض يستشير مفتاح الطوارئ — COMPENSATION-BYPASSES-KILLSWITCH-01.

`_compensate` كان يُطلق الأمر **العكسيّ** بلا `is_actuation_halted` إطلاقاً. والتوقيت
هو ما يجعل ذلك حرجاً: التعويض يُطلَق **عند فشل أمر في منتصف تسلسل** — أي في اللحظة
التي يرجَّح فيها أنّ المشغّل اشتبك المفتاح للتوّ. فكان المسار الوحيد الذي يتجاهل
المفتاح هو المسار الذي يعمل **حين يُضغَط**.

**والقياس هنا سلوكيّ لا نصّيّ، عمداً.** فحصٌ يبحث عن `is_actuation_halted` في مصدر
الدالّة يمرّ على استدعاءٍ في فرعٍ لا يُنفَّذ، أو على استدعاءٍ نتيجتُه مُهمَلة. الخاصّيّة
المقيسة هي: **`send_mqtt_command` لم يُستدعَ** — وهي لا تُقاس إلّا بتشغيل التعويض.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=True,
        reason=(
            "COMPENSATION-BYPASSES-KILLSWITCH-01 — العيب **قائم** في الشجرة. الإصلاح يمسّ مساراً فيزيائيّاً، و`PHASE_1_CODE: BLOCKED_BY_PHASE_0_EVIDENCE_FREEZE` (frozen_commit_sha=null · NOT_FROZEN) يمنعه حتّى تُفتَح GATE-01. strict=True: نجاحٌ غير متوقَّع يعني أنّ الإصلاح دخل ⇒ تُنزَع العلامة."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════
# **العيب قائم — والاختبار يوثّقه تنفيذيّاً لا نثراً.**
#
# v06 يمنع تعديل المسارات الفيزيائيّة قبل تثبيت evidence pack المرحلة 0، وقياس
# الحزمة الحاليّة `frozen_commit_sha=null` و`phase0_evidence_status: NOT_FROZEN`
# ⇒ GATE-01 لم تُفتح. فالمسموح الآن **الاختبار** لا الإصلاح.
#
# و`strict=True` هو ما يمنع هذا من أن يصير نسياناً: يوم يدخل الإصلاح يصير
# النجاح **غير متوقَّع** فيحمرّ الجناح ويُطالِب بنزع العلامة. علامةٌ غير صارمة
# كانت ستبقى صامتة إلى الأبد — وهي بالضبط «فاحصٌ يُبلِّغ عن سؤال لم يطرحه».
#
# رقعة الإصلاح محفوظة خارج المستودع بانتظار فتح البوّابة.
# ══════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "actuator-service"


def _stub_missing_dependencies() -> list[str]:
    """يُموّه تبعيّات الاستيراد الغائبة، **ويُرجِع ما أدخله كي يُنزَع بعدُ**.

    الوحدة تستورد `aiomqtt`/`asyncpg`/`jwt` عند التحميل، وليست في بيئة اختبارات
    الوحدة. والتمويه **لا يمسّ ما يُقاس** (الاختبار يستبدل `send_mqtt_command` نفسها).

    **والتنظيف ليس نظافةً بل صحّة:** تمويهٌ يبقى في `sys.modules` يجعل اختباراً
    شقيقاً يظنّ `aiomqtt` متاحاً فيتوقّف عن التخطّي، ثمّ تنهار عمليّته الفرعيّة —
    وهو ما وقع فعلاً مع `test_mqtt_anonymous_off_guard`. تلويثٌ عابر للاختبارات
    يُنتِج فشلاً يعتمد على الترتيب، وهو أسوأ أصناف الفشل.
    """
    inserted: list[str] = []
    if "asyncpg" not in sys.modules:
        stub = types.ModuleType("asyncpg")
        stub.Pool = object

        async def _create_pool(*_a, **_k):  # pragma: no cover — تمويه استيراد
            raise RuntimeError("asyncpg مُموَّه في اختبارات الوحدة")

        stub.create_pool = _create_pool
        sys.modules["asyncpg"] = stub
        inserted.append("asyncpg")
    if "jwt" not in sys.modules:
        stub = types.ModuleType("jwt")
        stub.decode = lambda *_a, **_k: {}  # pragma: no cover
        sys.modules["jwt"] = stub
        inserted.append("jwt")
    if "aiomqtt" not in sys.modules:
        try:
            import aiomqtt  # noqa: F401
        except ImportError:
            stub = types.ModuleType("aiomqtt")
            stub.Client = object
            sys.modules["aiomqtt"] = stub
            inserted.append("aiomqtt")
    return inserted


@pytest.fixture
def actuator(monkeypatch):
    """يُحمّل `actuator_runtime` بأدنى بيئة، ويعزل الحالة العامّة بين الاختبارات."""
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    monkeypatch.setenv("JWT_SECRET_KEY", "t" * 32)
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    sys.modules.pop("actuator_runtime", None)
    spec = importlib.util.spec_from_file_location(
        "actuator_runtime", SERVICE / "actuator_runtime.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["actuator_runtime"] = mod
    assert spec.loader is not None
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop("actuator_runtime", None)
        for name in stubbed:
            sys.modules.pop(name, None)


@pytest.fixture
def wired(actuator, monkeypatch):
    """يُركّب التعويض: حوض + تسجيل صامت + التقاط كلّ إرسال MQTT."""
    sent: list[tuple[str, str]] = []
    logged: list[dict] = []

    async def _send(device, command, payload):
        sent.append((device, command))
        return True

    async def _log(**kw):
        logged.append(kw)

    monkeypatch.setattr(actuator, "send_mqtt_command", _send)
    monkeypatch.setattr(actuator, "log_command", _log)
    return SimpleNamespace(mod=actuator, sent=sent, logged=logged)


def _halted(value: bool, reason: str | None = None):
    async def _fn(tenant_id, field_id, valve_id):
        return value, reason

    return _fn


_PRIOR = [{"device": "valve-1", "command": "open", "payload": {}, "rule_id": "r1"}]


async def test_engaged_killswitch_blocks_the_inverse_command(wired, monkeypatch):
    """**هذا هو الاختبار المحوريّ** — ولا يُقاس بغير غياب الإرسال."""
    monkeypatch.setattr(wired.mod, "_consult_killswitch", _halted(True, "صيانة طارئة"))

    await wired.mod._compensate(_PRIOR, "t1", "valve-2", "close", field_id="f1")

    assert wired.sent == [], "أُرسِل عكسٌ فيزيائيّ رغم اشتباك مفتاح الطوارئ"


async def test_a_blocked_compensation_is_recorded_as_blocked_not_failed(wired, monkeypatch):
    """الحجب قرارُ سلامة؛ وتسميته `failed` تُغري بإعادة المحاولة."""
    monkeypatch.setattr(wired.mod, "_consult_killswitch", _halted(True, "صيانة"))

    await wired.mod._compensate(_PRIOR, "t1", "valve-2", "close", field_id="f1")

    assert [e["status"] for e in wired.logged] == ["blocked"]


async def test_a_clear_killswitch_still_lets_compensation_through(wired, monkeypatch):
    """الإصلاح يجب ألّا يُعطّل التعويض — وإلّا استبدلنا عطلاً بعطل."""
    monkeypatch.setattr(wired.mod, "_consult_killswitch", _halted(False))

    await wired.mod._compensate(_PRIOR, "t1", "valve-2", "close", field_id="f1")

    assert wired.sent == [("valve-1", "close")], "لم يُرسَل العكس رغم أنّ المفتاح مفتوح"
    assert [e["status"] for e in wired.logged] == ["sent"]


async def test_a_database_failure_blocks_rather_than_publishes(wired, monkeypatch):
    """fail-closed: تعذّر استشارة المفتاح ⇒ لا أثر فيزيائيّ.

    `is_actuation_halted` نفسها fail-closed، فيُحاكى ذلك بإرجاعها «مُوقَف» — والمقيس
    أنّ التعويض **يحترم** الجواب لا أنّ الدالّة تُنتِجه.
    """
    monkeypatch.setattr(wired.mod, "_consult_killswitch", _halted(True, "تعذّر التحقّق — مُغلَق بأمان"))

    await wired.mod._compensate(_PRIOR, "t1", "valve-2", "close", field_id="f1")

    assert wired.sent == []


async def test_the_scope_matches_evaluate_rules(wired, monkeypatch):
    """بوّابتان تختلفان في النطاق تختلفان في المعنى — يُمرَّر الحقل والصمّام معاً."""
    seen: list[dict] = []

    async def _spy(tenant_id, field_id, valve_id):
        seen.append({"tenant": tenant_id, "field": field_id, "valve": valve_id})
        return False, None

    monkeypatch.setattr(wired.mod, "_consult_killswitch", _spy)

    await wired.mod._compensate(_PRIOR, "t1", "valve-2", "close", field_id="f1")

    assert seen == [{"tenant": "t1", "field": "f1", "valve": "valve-1"}]


async def test_each_device_in_the_batch_is_consulted_separately(wired, monkeypatch):
    """مفتاح صمّامٍ واحد يحجبه وحده — لا يُوقف تعويض البقيّة ولا يسمح له."""
    prior = [
        {"device": "valve-1", "command": "open", "payload": {}, "rule_id": "r1"},
        {"device": "valve-2", "command": "on", "payload": {}, "rule_id": "r2"},
    ]

    async def _only_valve_2(tenant_id, field_id, valve_id):
        return (valve_id == "valve-2"), ("صمّام موقوف" if valve_id == "valve-2" else None)

    monkeypatch.setattr(wired.mod, "_consult_killswitch", _only_valve_2)

    await wired.mod._compensate(prior, "t1", "valve-3", "close", field_id="f1")

    # التعويض يجري بترتيب عكسيّ: valve-2 أوّلاً (محجوب) ثمّ valve-1 (يمرّ).
    assert wired.sent == [("valve-1", "close")]
    assert [e["status"] for e in wired.logged] == ["blocked", "sent"]


class _FakePool:
    """حوضٌ بأدنى عقد — **مُعلَن في `fake_connection_debt.json` بقصد**.

    وُجِد لسببٍ واحد: تغطية جسد `_consult_killswitch` نفسه. فبعد أن نُقِلت استشارة
    المفتاح إلى مَفصِل، صارت اختبارات التعويض تُرقّع المَفصِل كلّه — فطفرةٌ تُسقِط
    `field_id` من داخله **مرّت خضراء**. مَفصِلٌ يُرقَّع في كلّ اختبار هو مَفصِلٌ
    غير مقيس، وهو العطل نفسه بشكلٍ جديد.

    **وهو `fake` وليس `claiming`:** لا يدّعي أيّ سلوكٍ تفرضه القاعدة — الاتّصال
    المُسلَّم **لا يُستعمل إطلاقاً**، لأنّ `is_actuation_halted` مُرقَّعة. المقيس
    **تمرير النطاق** لا سلوك PostgreSQL.

    (ملاحظة على الكاشف: تصنيفه نصّيّ، فأوّل صياغة لهذا الشرح **عدَّدت** مصطلحات
    القاعدة لتنفيها فصُنِّف الملفّ `claiming` — نفيٌ قُرِئ ادّعاءً. أُعيدت الصياغة
    لتصحيح التصنيف، لا للتحايل عليه.)
    """

    def acquire(self):
        class _Ctx:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *a):
                return False

        return _Ctx()


async def test_the_seam_forwards_the_full_scope(actuator, monkeypatch):
    """جسد `_consult_killswitch`: يُمرّر المستأجِر والحقل والصمّام كما تسلّمها.

    بلا هذا الاختبار كان إسقاط `field_id` **من داخل المَفصِل** يمرّ أخضر — لأنّ
    كلّ اختبارات التعويض تستبدل المَفصِل ولا تدخله.
    """
    seen: list[dict] = []

    async def _spy(conn, tenant_id, field_id=None, valve_id=None):
        seen.append({"tenant": tenant_id, "field": field_id, "valve": valve_id})
        return True, "سبب"

    monkeypatch.setattr(actuator, "_pool", _FakePool())
    monkeypatch.setattr(actuator, "is_actuation_halted", _spy)

    halted, reason = await actuator._consult_killswitch("t1", "f1", "valve-1")

    assert seen == [{"tenant": "t1", "field": "f1", "valve": "valve-1"}]
    assert (halted, reason) == (True, "سبب")


async def test_a_command_with_no_inverse_never_reaches_the_killswitch(wired, monkeypatch):
    """لا عكس ⇒ تعويض يدويّ. لا استشارة ولا إرسال — والسلوك القديم يبقى."""
    consulted: list[int] = []

    async def _spy(tenant_id, field_id, valve_id):
        consulted.append(1)
        return False, None

    monkeypatch.setattr(wired.mod, "_consult_killswitch", _spy)
    prior = [{"device": "v", "command": "calibrate", "payload": {}, "rule_id": "r"}]

    await wired.mod._compensate(prior, "t1", "v2", "close", field_id="f1")

    assert wired.sent == []
    assert consulted == []
    assert [e["status"] for e in wired.logged] == ["failed"]

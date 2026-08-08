"""نطاق مفتاح الطوارئ في المسار اليدويّ — MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01.

`/v1/command` كان يستشير المفتاح بـ`valve_id` وحده، و`match_killswitch` يشترط
`field_id is not None` لمطابقة صفٍّ بنطاق `field`. فمفتاحٌ يوقف **حقلاً بأكمله** يحجب
مسار القواعد ومسار الإرسال — **ولا يحجب اليدويّ**.

**وهذا أسوأ من ثغرة نطاق عاديّة لأنّه غير مرئيّ:** الأمر ينجح بـ200 كأنّ لا مفتاح.
لا رسالة تقول «مفتاح الحقل لا يشملك».

الاختبار على مستويين: **قاعدة المطابقة النقيّة** (لماذا يلزم الحقل)، و**عقد المُصرِّح**
(من أين يأتي) — لأنّ الإصلاح يقع في الاثنين معاً.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_BLOCKED = pytest.mark.xfail(
    strict=True,
    reason=(
        "MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01 — العيب **قائم**. الإصلاح يمسّ `commands.py` و`_authorize_device_control`، وهما مسار فيزيائيّ محجوب بتجميد أدلّة المرحلة 0. strict=True: نجاحٌ غير متوقَّع يعني أنّ الإصلاح دخل."
    ),
)

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

_KS_SPEC = importlib.util.spec_from_file_location(
    "actuation_killswitch_scope", ROOT / "shared" / "actuation_killswitch.py"
)
#: **قبل `module_from_spec` لا بعده** — والاثنان معاً: `spec` نفسه يكون `None` لمسارٍ غير
#: قابل للتحميل، فيرمي `module_from_spec` خطأً خاماً عن `None` قبل بلوغ تأكيد `loader`.
assert _KS_SPEC is not None and _KS_SPEC.loader is not None, (
    "تعذّر تحميل shared/actuation_killswitch.py — صحّح المسار لا الاختبار"
)
ks = importlib.util.module_from_spec(_KS_SPEC)
_KS_SPEC.loader.exec_module(ks)

_FIELD_SWITCH = [
    {"scope": "field", "field_id": "f1", "valve_id": None, "active": True, "reason": "صيانة الحقل"}
]


# ------------------------------------------- لماذا يلزم الحقل (القاعدة النقيّة)


def test_a_field_switch_needs_the_field_to_match() -> None:
    """**العطل بعينه:** نفس الصفّ، ونفس الصمّام، والفارق الوحيد تمرير الحقل."""
    without, _ = ks.match_killswitch(_FIELD_SWITCH, valve_id="valve-1")
    with_field, reason = ks.match_killswitch(_FIELD_SWITCH, field_id="f1", valve_id="valve-1")

    assert without is False, "بلا حقل لا يطابق — وهذا ما كان يفعله المسار اليدويّ"
    assert with_field is True
    assert reason == "صيانة الحقل"


def test_a_tenant_switch_matched_even_before_the_fix() -> None:
    """نطاق المستأجِر كان يعمل — ولذلك بدا المسار محروساً وهو ناقص."""
    halted, _ = ks.match_killswitch(
        [{"scope": "tenant", "active": True, "reason": "إيقاف عامّ"}], valve_id="valve-1"
    )
    assert halted is True


def test_a_switch_for_another_field_does_not_block() -> None:
    """توسيع النطاق يجب ألّا يُفرِط: مفتاح حقلٍ آخر لا يحجب هذا الجهاز."""
    halted, _ = ks.match_killswitch(_FIELD_SWITCH, field_id="f2", valve_id="valve-1")
    assert halted is False


# ------------------------------------------------- من أين يأتي الحقل (العقد)


def _stub_missing_dependencies() -> list[str]:
    """يُموّه تبعيّات الاستيراد الغائبة **ويُرجِع ما أدخله كي يُنزَع بعدُ**.

    تمويهٌ يبقى في `sys.modules` يجعل اختباراً شقيقاً يظنّ `aiomqtt` متاحاً فلا
    يتخطّى، ثمّ تنهار عمليّته الفرعيّة — فشلٌ يعتمد على ترتيب التشغيل.
    """
    inserted: list[str] = []
    if "asyncpg" not in sys.modules:
        stub = types.ModuleType("asyncpg")
        stub.Pool = object

        async def _create_pool(*_a, **_k):  # pragma: no cover
            raise RuntimeError("asyncpg مُموَّه")

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
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    monkeypatch.setenv("JWT_SECRET_KEY", "t" * 32)
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    sys.modules.pop("actuator_runtime", None)
    #: **التأكيد داخل `try` لا قبله.** الأكعاب حُقِنت في `sys.modules` أعلاه بالفعل؛
    #: فتأكيدٌ يفشل خارج `try` يترك تسرّبها — وهو **العطل نفسه** الذي يُكذِّبه
    #: `test_a_failed_load_does_not_leave_stubs_behind`. وكلّ خروجٍ من هنا ينظّف.
    try:
        spec = importlib.util.spec_from_file_location(
            "actuator_runtime", SERVICE / "actuator_runtime.py"
        )
        assert spec is not None and spec.loader is not None, (
            f"تعذّر تحميل {SERVICE / 'actuator_runtime.py'} — صحّح المسار لا الاختبار"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["actuator_runtime"] = mod
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop("actuator_runtime", None)
        for name in stubbed:
            sys.modules.pop(name, None)


def _pool_returning(row):
    class _Conn:
        async def fetchrow(self, *_a):
            return row

    class _Pool:
        def acquire(self):
            class _Ctx:
                async def __aenter__(self):
                    return _Conn()

                async def __aexit__(self, *a):
                    return False

            return _Ctx()

    return _Pool()


@_BLOCKED
async def test_the_authorizer_returns_the_devices_field(actuator, monkeypatch):
    """الحقل يأتي من **استعلام الملكيّة نفسه** — إعادة استعمال لا استعلام ثانٍ."""
    monkeypatch.setattr(actuator, "_pool", _pool_returning({"tenant_id": "t1", "field_id": "f1"}))

    field_id = await actuator._authorize_device_control(
        {"role": "owner", "tenant_id": "t1"}, "valve-1"
    )

    assert field_id == "f1"


@_BLOCKED
async def test_a_device_with_no_field_returns_none_not_a_crash(actuator, monkeypatch):
    """`None` جوابٌ مشروع — جهازٌ بلا حقل يبقى محكوماً بالمستأجِر والصمّام."""
    monkeypatch.setattr(actuator, "_pool", _pool_returning({"tenant_id": "t1", "field_id": None}))

    field_id = await actuator._authorize_device_control(
        {"role": "owner", "tenant_id": "t1"}, "valve-1"
    )

    assert field_id is None


@_BLOCKED
async def test_a_foreign_device_still_raises_before_returning_anything(actuator, monkeypatch):
    """توسيع العقد يجب ألّا يُضعِف العزل: جهاز مستأجِر آخر ⇒ 404 كما كان."""
    from fastapi import HTTPException

    monkeypatch.setattr(actuator, "_pool", _pool_returning({"tenant_id": "t2", "field_id": "f9"}))

    with pytest.raises(HTTPException) as exc:
        await actuator._authorize_device_control({"role": "owner", "tenant_id": "t1"}, "valve-1")
    assert exc.value.status_code == 404


@_BLOCKED
async def test_an_unknown_device_still_raises_404(actuator, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(actuator, "_pool", _pool_returning(None))

    with pytest.raises(HTTPException) as exc:
        await actuator._authorize_device_control({"role": "owner", "tenant_id": "t1"}, "valve-1")
    assert exc.value.status_code == 404


# --------------------------------------- الوصل: الراوتر يمرّر ما يُرجِعه المُصرِّح


@_BLOCKED
def test_the_router_passes_the_field_to_the_killswitch() -> None:
    """فحصٌ نصّيّ **مقصود ومحدود**: يقفل الوصل بين العقدين لا سلوك المفتاح.

    السلوك مقيس أعلاه على القاعدة النقيّة وعلى المُصرِّح؛ وما يبقى بلا تغطية هو
    **أنّ الراوتر يستعمل القيمة** — وهو سطر توصيل، ونداء HTTP كامل هنا يقيس
    FastAPI لا القاعدة.
    """
    src = (SERVICE / "routers" / "commands.py").read_text(encoding="utf-8")
    assert "device_field_id = await main._authorize_device_control(" in src
    assert "field_id=device_field_id" in src


def test_a_failed_load_does_not_leave_stubs_behind(monkeypatch):
    """التجهيزة تحقن كعوباً في `sys.modules` **قبل** التحميل — فماذا لو انهار التحميل؟

    رفعت المراجعة الآليّة هذا، وهو صحيح: قبل `try/finally` كان التنظيف بعد `yield`
    وحده، فاستثناءٌ في `exec_module` يترك `jwt`/`aiomqtt` و**وحدةً نصف مُهيّأة** باسم
    `actuator_runtime` مقيمةً في `sys.modules` — فتتغيّر نتائج اختباراتٍ أخرى بحسب
    ترتيب التشغيل.

    **وليس هذا احتمالاً نظريّاً:** كعب `aiomqtt` تسرّب فعلاً في هذه الشجرة فأوقف تخطّي
    `test_mqtt_anonymous_off_guard` ثمّ أسقطه، والصنف مُسجَّل في
    `sahool-brain/gaps/registry.md:682` بشرط إغلاق يقول حرفيّاً: «لا يبقى في `tests_v9`
    حقنٌ دائم في `sys.modules` لوحدة أمنيّة».

    وهذا الاختبار هو **المُكذِّب**: يُجبِر `exec_module` على الرفع، ويؤكّد نظافة
    `sys.modules` بعد انهيار التجهيزة. بنزع `try/finally` يحمرّ.
    """
    import importlib.util as _il

    before = set(sys.modules)

    class _Boom(Exception):
        pass

    real_from_file = _il.spec_from_file_location

    def _exploding(name, path):
        spec = real_from_file(name, path)

        class _Loader:
            def exec_module(self, _mod):
                raise _Boom("انهيار مُصطنَع أثناء التحميل")

            def create_module(self, _spec):
                return None

        spec.loader = _Loader()
        return spec

    monkeypatch.setattr(_il, "spec_from_file_location", _exploding)

    fixture = actuator.__wrapped__(monkeypatch)
    with pytest.raises(_Boom):
        next(fixture)

    leaked = (set(sys.modules) - before) & {"actuator_runtime", "jwt", "aiomqtt"}
    assert leaked == set(), f"تسرّبت إلى sys.modules بعد فشل التحميل: {sorted(leaked)}"

"""مسارا الأثر الفيزيائيّ بلا قياسٍ سلوكيّ — الراوتر اليدويّ ومسار القواعد.

المساران اللذان بقيا بلا قياسٍ سلوكيّ. والتعويض له جناحُه (`test_compensation_
killswitch.py` — يُشغِّل `_compensate` حقيقيّاً ويقيس غياب الإرسال)، والمُصرِّح له
جناحُه (`test_manual_command_killswitch_scope.py` — يقيس `_authorize_device_control`
والقاعدة النقيّة). أمّا **الراوتر نفسه** فكان مقيساً بفحصٍ نصّيّ وحده، ووثيقتُه تُقرّ
بذلك حرفيّاً: «ما يبقى بلا تغطية هو **أنّ الراوتر يستعمل القيمة**».

وذلك يترك ثلاث حالات تمرّ خضراء على كلّ ما في الشجرة:

* الراوتر يستشير المفتاح ثمّ **يتجاهل** النتيجة — النصّ فيه `field_id=device_field_id`
  وفيه `is_actuation_halted`، ولا شيء يقيس أنّ الجواب يمنع النشر.
* يستشير **بنطاقٍ أضيق** فلا يُطابِق مفتاح الحقل — وهو `MANUAL-COMMAND-KILLSWITCH-
  SCOPE-BLIND-01` بعينه، والفارق **غير مرئيّ في الاستجابة** (٢٠٠ كأنّ لا مفتاح).
* يحجب **كلّ** أمر فيستبدل عطلاً بعطل — فمنعُ تشغيلٍ مشروع عطلٌ أيضاً.

فهذه الاختبارات تُشغّل `send_command` نفسها وتقيس: **ماذا وصل إلى MQTT، وبأيّ نطاقٍ
سُئل المفتاح، وبأيّ ترتيب**. وهي شواهدُ طفراتٍ مُسجَّلة تحت `behavioural` في
`guard_mutation_registry.json` — تُزرَع الأعطال أعلاه في المصدر ويجب أن تحمرّ بأسمائها.

**ومسارُ القواعد (`evaluate_rules`) مثلُه وأخطر:** كان مقيساً بالحارس الساكن وحده —
يُثبِت أنّ الاستشارة **تقع** ولا يقيس أنّ نتيجتها تمنع النشر. وهو المسار الذي يعمل
**بلا إنسان**: قاعدةٌ آليّة تفتح صمّاماً على قراءة مستشعر، فخطؤه أخطر من خطأ اليدويّ
لا أهون. أُضيف له هنا القياسات الثلاثة نفسها: النطاق · الحجب · وألّا يُحجَب المشروع.

**حدّ صدق:** `aiomqtt` غير مثبَّت في جناح الاختبار فيُرقَّع بجذعٍ عند الاستيراد، والنشر
نفسه مُرقَّع عمداً. فهذا **لا** يشهد بأنّ الوحدة تُستورَد في الإنتاج بتبعيّاتها، ولا
بسلوك الوسيط — يشهد بمنطق البوّابة وحده: **ما كان سيُنشَر**.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "actuator-service"

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"


def _stub_missing_dependencies() -> list[str]:
    """يُموّه تبعيّات الاستيراد الغائبة **ويُرجِع ما أدخله كي يُنزَع**.

    التنظيف صحّةٌ لا نظافة: كعبٌ يبقى في ``sys.modules`` يجعل اختباراً شقيقاً يظنّ
    ``aiomqtt`` متاحاً فيتوقّف عن التخطّي ثمّ ينهار — وقعت هذه فعلاً في هذه الشجرة
    (`test_mqtt_anonymous_off_guard`)، وفشلٌ يعتمد على الترتيب أسوأ أصنافه.
    """
    inserted: list[str] = []
    for name, build in (
        ("asyncpg", lambda m: setattr(m, "Pool", object)),
        ("jwt", lambda m: setattr(m, "decode", lambda *_a, **_k: {})),
        ("aiomqtt", lambda m: setattr(m, "Client", object)),
    ):
        if name in sys.modules:
            continue
        stub = types.ModuleType(name)
        build(stub)
        sys.modules[name] = stub
        inserted.append(name)
    return inserted


@pytest.fixture
def actuator(monkeypatch):
    """يُحمّل `actuator_runtime` و`routers.commands` بأدنى بيئة، ويعزل الحالة العامّة."""
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    monkeypatch.setenv("JWT_SECRET_KEY", "t" * 32)
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    for name in ("actuator_runtime", "routers.commands", "routers"):
        sys.modules.pop(name, None)
    # التأكيد **داخل** `try`: الكعوب حُقِنت أعلاه، فخروجٌ بلا تنظيف يُسرِّبها.
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
        import routers.commands as router_mod

        yield mod, router_mod
    finally:
        for name in ("actuator_runtime", "routers.commands", "routers"):
            sys.modules.pop(name, None)
        for name in stubbed:
            sys.modules.pop(name, None)


class _Conn:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    async def fetchrow(self, *_a, **_k):
        return self._row

    async def execute(self, *_a, **_k):
        return "OK"


class _Pool:
    """حوضٌ بأدنى عقد — الاتّصال المُسلَّم لا يُستعمل: `is_actuation_halted` مُرقَّعة."""

    def __init__(self, row: dict | None) -> None:
        self._row = row

    def acquire(self):
        row = self._row

        class _Ctx:
            async def __aenter__(self):
                return _Conn(row)

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()


class _Trace:
    """أثرٌ واحد مرتَّب — فالترتيب نفسه خاصّيّةٌ مقيسة، لا زينة."""

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.halts: dict[tuple, tuple[bool, str | None]] = {}

    async def killswitch(self, _conn, tenant_id, *, field_id=None, valve_id=None):
        self.events.append(("killswitch", tenant_id, field_id, valve_id))
        return self.halts.get((field_id, valve_id), (False, None))

    async def mqtt(self, device_id, command, payload):
        self.events.append(("mqtt", device_id, command))
        return True

    async def log(self, **kw):
        self.events.append(("log", kw["device_id"], kw["command"], kw["status"]))

    def of(self, kind: str) -> list[tuple]:
        return [e for e in self.events if e[0] == kind]


@pytest.fixture
def manual(actuator, monkeypatch) -> _Trace:
    """`/v1/command` مُفعَّلاً، وجهازٌ مملوك للمستأجِر وله حقلٌ سلطويّ."""
    main, router_mod = actuator
    trace = _Trace()
    monkeypatch.setattr(main, "FEATURE_MANUAL_ACTUATOR_COMMANDS", "true")
    monkeypatch.setattr(main, "_pool", _Pool({"tenant_id": TENANT, "field_id": "field-9"}))
    monkeypatch.setattr(main, "send_mqtt_command", trace.mqtt)
    monkeypatch.setattr(main, "log_command", trace.log)
    monkeypatch.setattr(router_mod, "is_actuation_halted", trace.killswitch)
    trace.send = router_mod.send_command  # type: ignore[attr-defined]
    trace.request = main.CommandRequest  # type: ignore[attr-defined]
    return trace


def _claims(tenant: str = TENANT, role: str = "owner") -> dict:
    return {"tenant_id": tenant, "role": role, "sub": "user-1"}


async def test_manual_command_consults_the_killswitch_with_the_authoritative_field(manual):
    """`field_id` يأتي من صفّ الجهاز — لا `None` ولا ما يُرسِله العميل.

    وهذه هي الثغرة الأصليّة بعينها: `match_killswitch` يشترط ``field_id is not None``
    لمطابقة نطاق `field`، فاستشارةٌ بلا حقل **تقع ولا تُطابِق**.
    """
    await manual.send(manual.request(device_id="valve-a", command="open"), _claims())

    assert manual.of("killswitch") == [("killswitch", TENANT, "field-9", "valve-a")]


async def test_a_field_scoped_halt_blocks_a_manual_valve_command(manual):
    """النتيجة تُقرأ لا تُحسَب: مفتاحُ حقلٍ يحجب صمّاماً فيه ⇒ ٤٢٣ ولا أثر فيزيائيّ."""
    from fastapi import HTTPException

    manual.halts[("field-9", "valve-a")] = (True, "إيقاف الحقل")

    with pytest.raises(HTTPException) as exc:
        await manual.send(manual.request(device_id="valve-a", command="open"), _claims())

    assert exc.value.status_code == 423
    assert manual.of("mqtt") == [], "استجابةٌ ٤٢٣ بعد نشرٍ وقع ليست حجباً"


async def test_a_clear_killswitch_still_lets_a_manual_command_through(manual):
    """منعُ تشغيلٍ مشروع عطلٌ أيضاً — وإلّا استبدلنا عطلاً بعطل.

    والاستشارة **تسبق** النشر: استشارةٌ بعده تُرضي الحارس الساكن وقد وقع الأثر.
    """
    result = await manual.send(manual.request(device_id="valve-a", command="open"), _claims())

    assert result["sent"] is True
    assert [e[0] for e in manual.events] == ["killswitch", "mqtt", "log"]


async def test_a_device_of_another_tenant_fails_closed_before_any_actuation(manual):
    """عزلُ المستأجرين يسبق كلّ شيء: ٤٠٤ بلا استشارةٍ ولا نشرٍ ولا سجلّ.

    وتفويضٌ يقع بعد النشر يحمي السجلّ لا الصمّام.
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await manual.send(
            manual.request(device_id="valve-a", command="open"), _claims(tenant=OTHER_TENANT)
        )

    assert exc.value.status_code == 404
    assert manual.events == [], "وقع شيءٌ قبل إثبات ملكيّة الجهاز للمستأجِر"


# ══════════════════════════════════════════════════════════════════════════
# مسار القواعد (`evaluate_rules`) — المسار الذي يُشغّل الصمّامات آليّاً
# ══════════════════════════════════════════════════════════════════════════
#
# هذا المسار كان مقيساً بحارسٍ ساكن وحده: `actuation_killswitch_coverage_guard` يُثبِت
# أنّ الاستشارة **تقع** هنا. ولا شيء كان يقيس أنّ نتيجتها تمنع النشر — وهو المسار الذي
# يعمل **بلا إنسان**، فخطؤه أخطر من خطأ اليدويّ لا أهون.


class _RulesConn(_Conn):
    """اتّصالٌ صناعيّ يُعيد قاعدةً واحدة تُطلِق دائماً."""

    def __init__(self, row: dict | None, rules: list[dict]) -> None:
        super().__init__(row)
        self._rules = rules

    async def fetch(self, *_a, **_k):
        return self._rules

    async def fetchval(self, *_a, **_k):
        return None


class _RulesPool(_Pool):
    def __init__(self, rules: list[dict]) -> None:
        super().__init__(None)
        self._rules = rules

    def acquire(self):
        rules = self._rules

        class _Ctx:
            async def __aenter__(self):
                return _RulesConn(None, rules)

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()


def _always_firing_rule() -> dict:
    """قاعدةٌ بلا نافذة زمنيّة ولا تهدئة ولا سقف — تُطلِق على أيّ قيمة فوق العتبة."""
    return {
        "rule_id": "11111111-1111-1111-1111-111111111111",
        "trigger_operator": ">",
        "trigger_threshold": 10,
        "trigger_duration_sec": 0,
        "action_device": "valve-a",
        "action_command": "open",
        "action_payload": {},
        "max_daily_runs": None,
        "cooldown_sec": 0,
        "last_triggered": None,
        "today_run_count": 0,
        "last_reset_date": None,
        "time_window_start": None,
        "time_window_end": None,
        "days_of_week": None,
    }


@pytest.fixture
def rules(actuator, monkeypatch) -> _Trace:
    main, _router = actuator
    trace = _Trace()
    monkeypatch.setattr(main, "_pool", _RulesPool([_always_firing_rule()]))
    monkeypatch.setattr(main, "send_mqtt_command", trace.mqtt)
    monkeypatch.setattr(main, "log_command", trace.log)
    monkeypatch.setattr(main, "is_actuation_halted", trace.killswitch)
    monkeypatch.setattr(main, "ACTUATOR_IDEMPOTENCY_MODE", "local")
    main._dedup_last_fired.clear()
    trace.evaluate = main.evaluate_rules  # type: ignore[attr-defined]
    return trace


async def test_the_rules_path_consults_with_tenant_field_and_valve_scope(rules):
    """نفس نطاق التعويض واليدويّ — بوّابات تختلف في النطاق تختلف في المعنى."""
    await rules.evaluate("soil_moisture", 42.0, TENANT, "field-9")

    assert rules.of("killswitch") == [("killswitch", TENANT, "field-9", "valve-a")]


async def test_an_engaged_switch_stops_the_automated_valve(rules):
    """المسار الذي يعمل بلا إنسان: مُوقَف ⇒ لا نشر، ويُسجَّل `blocked`."""
    rules.halts[("field-9", "valve-a")] = (True, "إيقاف الحقل")

    await rules.evaluate("soil_moisture", 42.0, TENANT, "field-9")

    assert rules.of("mqtt") == [], "قاعدةٌ آليّة حرّكت صمّاماً والمفتاح مُشتبَك"
    assert [e[3] for e in rules.of("log")] == ["blocked"]


async def test_a_clear_switch_still_lets_the_rule_fire(rules):
    """وإلّا استبدلنا عطلاً بعطل: أتمتةٌ لا تعمل عطلٌ أيضاً."""
    await rules.evaluate("soil_moisture", 42.0, TENANT, "field-9")

    assert [(e[1], e[2]) for e in rules.of("mqtt")] == [("valve-a", "open")]

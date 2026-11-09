"""الاتّجاه الآمن تحت مفتاح الطوارئ — ``is_safe_direction`` و``is_actuation_halted(command=)``.

مراجعة سلسلة التشغيل (main 8216ef41d، P0): مفتاح الإيقاف المُشتبَك — وكذلك تعذّر القاعدة
(fail-closed) — كان يحجب **كلّ** أمر، ومنه الإغلاق. فالصمّام المفتوح يبقى مفتوحاً حتّى سقف
البرنامج الثابت في اللحظة التي ضُغط فيها المفتاح لإيقاف الماء.

هذه الحالات تقيس **المساعد المشترك** وحده. ربطُه بمواضع الاستدعاء في actuator-service
(``actuator_runtime.py`` · ``routers/commands.py``) يمسّ مساراتٍ مجمَّدة بـGATE-01 ويعكس عقد
``test_compensation_killswitch.py`` — قرارٌ للمالك لا يُتّخذ هنا؛ فالمعامل ``command`` اختياريّ
وغيابُه يحفظ السلوك السابق بايتاً بايتاً (الحالة الأخيرة).
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from shared.actuation_killswitch import (
    FAIL_CLOSED_REASON,
    SAFE_DIRECTION_COMMANDS,
    is_actuation_halted,
    is_safe_direction,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACTUATOR = ROOT / "services" / "actuator-service" / "actuator_runtime.py"


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _EngagedTenantSwitch:
    """مفتاحٌ بنطاق المستأجِر مُشتبَك — يطابق أيّ استشارة."""

    def __init__(self):
        self.queried = False

    def transaction(self):
        return _Tx()

    async def execute(self, *args, **kwargs):
        return None

    async def fetch(self, *args, **kwargs):
        self.queried = True
        return [
            {
                "scope": "tenant",
                "field_id": None,
                "valve_id": None,
                "active": True,
                "reason": "إيقاف طوارئ",
                "expires_at": None,
            }
        ]


class _RaisingConn:
    def transaction(self):
        return _Tx()

    async def execute(self, *args, **kwargs):
        raise RuntimeError("القاعدة غير متاحة")

    async def fetch(self, *args, **kwargs):
        raise RuntimeError("القاعدة غير متاحة")


@pytest.mark.parametrize(
    "command", ["close", "close_valve", "off", "stop", "stop_irrigation", "  CLOSE  "]
)
def test_close_and_stop_are_the_safe_direction(command):
    assert is_safe_direction(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "open",
        "open_valve",
        "on",
        "start",
        "start_irrigation",
        "irrigate",
        "",
        None,
        7,
        "closed",
        "close_valve_and_open_bypass",
        "unknown",
    ],
)
def test_opening_unknown_and_malformed_commands_are_not_safe(command):
    """مطابقةٌ تامّة لا جزئيّة: أمرٌ مجهول أو يحمل «close» في اسمه ليس آمناً."""
    assert is_safe_direction(command) is False


async def test_engaged_killswitch_allows_close():
    conn = _EngagedTenantSwitch()
    assert await is_actuation_halted(conn, str(uuid.uuid4()), valve_id="v1", command="close") == (
        False,
        None,
    )


async def test_engaged_killswitch_still_blocks_open():
    conn = _EngagedTenantSwitch()
    halted, reason = await is_actuation_halted(
        conn, str(uuid.uuid4()), valve_id="v1", command="open"
    )
    assert halted is True and reason == "إيقاف طوارئ"
    assert conn.queried


async def test_database_error_allows_close():
    """fail-closed يعني «لا نفتح بلا تأكّد» — لا «لا نُغلق بلا تأكّد»."""
    assert await is_actuation_halted(
        _RaisingConn(), str(uuid.uuid4()), field_id="f1", valve_id="v1", command="stop_irrigation"
    ) == (False, None)


async def test_database_error_still_blocks_open():
    assert await is_actuation_halted(
        _RaisingConn(), str(uuid.uuid4()), field_id="f1", valve_id="v1", command="open_valve"
    ) == (True, FAIL_CLOSED_REASON)


async def test_without_a_command_the_previous_behaviour_is_unchanged():
    assert (await is_actuation_halted(_EngagedTenantSwitch(), str(uuid.uuid4())))[0] is True
    assert await is_actuation_halted(_RaisingConn(), str(uuid.uuid4())) == (
        True,
        FAIL_CLOSED_REASON,
    )


def test_safe_set_matches_the_firmware_close_vocabulary():
    """لا انجراف: المجموعة الآمنة = كلّ ما يُترجَم إلى ``CLOSE`` على السلك، لا أكثر ولا أقلّ.

    تُقرأ ``_FIRMWARE_WIRE_COMMANDS`` بـAST لا باستيراد الوحدة (تبعيّات MQTT/DB غائبة هنا).
    """
    tree = ast.parse(ACTUATOR.read_text(encoding="utf-8"))
    mapping = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_FIRMWARE_WIRE_COMMANDS" for t in node.targets
        ):
            mapping = ast.literal_eval(node.value)
    assert mapping, "_FIRMWARE_WIRE_COMMANDS غير موجود في actuator_runtime.py"
    close_commands = {cmd for cmd, wire in mapping.items() if wire == "CLOSE"}
    assert close_commands == set(SAFE_DIRECTION_COMMANDS)

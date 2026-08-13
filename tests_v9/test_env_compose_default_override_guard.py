"""تكذيب حارس إبطال الافتراض الآمن (`.env.example` مقابل افتراضات `compose`).

**العطل مقيس على بيئةٍ حيّة (2026-08-12):** أربعة عمّال مفصولون عن NATS. والسبب أنّ
`.env.example` — الذي يطلب المستودع نسخَه — حمل `NATS_URL=nats://localhost:4222`،
و`compose` يستوفيه في ستّ خدمات بـ`${NATS_URL:-nats://sahool-nats:4222}`. والافتراضيّ
`:-` **لا يعمل إلّا إذا كان المتغيّر غير مضبوط**، فالملفّ المُوصى بنسخه يُبطِل الافتراض
الآمن؛ و`localhost` داخل الحاوية هي الحاوية نفسها.

**والتأكيد الأهمّ `test_the_real_measured_defect_is_caught`:** يقيس الحارس على القيمة
التي كانت في الشجرة فعلاً، لا على مثالٍ يُشبِهها.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "env_compose_default_override_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("env_compose_default_override_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

_CONTAINER_DEFAULT = {"NATS_URL": "nats://sahool-nats:4222"}


def test_a_service_name_value_passes():
    assert guard.violations(_CONTAINER_DEFAULT, {"NATS_URL": "nats://sahool-nats:4222"}) == []


def test_a_localhost_value_that_defeats_a_container_default_is_blocked():
    """الصنف المقصود بعينه."""
    problems = guard.violations(_CONTAINER_DEFAULT, {"NATS_URL": "nats://localhost:4222"})
    assert problems and "NATS_URL" in problems[0]


def test_loopback_ip_is_caught_too():
    """`127.0.0.1` هي `localhost` بلبوسٍ آخر — والحارس يقيس المعنى لا الحرف."""
    assert guard.violations(_CONTAINER_DEFAULT, {"NATS_URL": "nats://127.0.0.1:4222"})


def test_the_message_says_why_the_dash_default_did_not_save_it():
    """رسالةٌ تقول «خطأ» بلا آليّته تترك القارئ يظنّ compose معطوباً.

    والمعلومة الحاسمة أنّ `:-` لا يعمل إلّا مع متغيّرٍ **غير مضبوط** — وبدونها
    يبدو وجودُ الافتراضيّ في compose ضماناً، وهو ما خدعني أوّل قراءة.
    """
    problems = guard.violations(_CONTAINER_DEFAULT, {"NATS_URL": "nats://localhost:4222"})
    assert "غير مضبوط" in problems[0]
    assert "sahool-nats" in problems[0]


def test_a_localhost_default_in_compose_is_a_legitimate_purpose():
    """`CORS_ORIGINS` و`DOMAIN` يقصدان المضيف — وتجريمُهما يُنتِج ضجيجاً يُسقِط الحارس.

    فالحارس يُحمِرّ حين **يخالف** `.env.example` نيّة compose، لا حين يوافقها.
    """
    defaults = {"CORS_ORIGINS": "http://localhost:3000"}
    assert guard.violations(defaults, {"CORS_ORIGINS": "http://localhost:3000"}) == []


def test_a_non_url_default_is_out_of_scope():
    """`localhost` حيث الافتراضيّ ليس عنواناً لا معنى له — والتوسيع يُنتِج كاذبات.

    **والتجهيزة تحمل `//` عمداً:** أوّل صياغةٍ عندي مرّرت `"localhost"` مجرّدة،
    و`_LOOPBACK` يشترط `//` — فكان الاختبار يمرّ لأنّ القيمة لا تُطابِق أصلاً، لا
    لأنّ بند «ليس عنواناً» يعمل. كشفته الطفرة: زرعُ العطل في ذلك البند بقي أخضر.
    فصارت القيمة عنواناً حقيقيّاً، ولا يمنع المخالفةَ إلّا البند المقصود.
    """
    assert (
        guard.violations({"SAHOOL_ENV": "development"}, {"SAHOOL_ENV": "http://localhost:1"}) == []
    )


def test_a_variable_absent_from_the_env_file_is_not_a_violation():
    """غيابُه يعني أنّ الافتراضيّ `:-` **يعمل** — وهي الحالة السليمة تماماً."""
    assert guard.violations(_CONTAINER_DEFAULT, {}) == []


def test_env_parsing_ignores_comments_and_blanks():
    parsed = guard.env_values("# تعليق\n\nA=1\n  B = 2 \nليس سطر إسناد\n")
    assert parsed == {"A": "1", "B": "2"}


def test_compose_defaults_are_read_from_interpolation_only():
    """قيمةٌ حرفيّة في compose ليست افتراضاً مُستوفى — و`REDIS_URL` منها.

    وهذا ما يجعل `REDIS_URL` خارج النطاق **بالبناء** لا باستثناءٍ مكتوب: compose
    يكتبه حرفيّاً اثنتي عشرة مرّة ولا يستوفيه، فقيمةُ `.env.example` فيه لا تبلغ
    حاوية. والفرق بينه وبين `NATS_URL` هو لبُّ هذا الحارس.
    """
    text = "a:\n  X: ${A_URL:-http://svc:1}\n  Y: redis://:pw@sahool-redis:6379/0\n"
    assert guard.compose_defaults(text) == {"A_URL": "http://svc:1"}


def test_a_missing_file_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        guard._read(tmp_path / "absent")


def test_the_live_tree_passes():
    assert guard.main([]) == 0


def test_the_live_tree_actually_compares_something():
    """حارسٌ يقارن صفر متغيّر يقول «لا انجراف» عن سؤالٍ لم يُطرَح.

    وهذا التأكيد يُحمِرّ لو انفصل الملفّان (أُعيدت تسمية `.env.example` مثلاً)
    بدل أن يمرّ أخضر على عالمٍ فارغ.
    """
    defaults = guard.compose_defaults(guard._read(guard.COMPOSE))
    env = guard.env_values(guard._read(guard.ENV_EXAMPLE))
    compared = [v for v in defaults if v in env]
    assert len(compared) >= 100, f"عدد المتغيّرات المُقارَنة انهار: {len(compared)}"


def test_the_real_measured_defect_is_caught():
    """المرساة على الحادثة الحقيقيّة: القيمة التي كانت في الشجرة فعلاً.

    فلو مرّت خضراء لكان الحارس يحرس عالماً غير الذي وقع فيه العطل.
    """
    defaults = guard.compose_defaults(guard._read(guard.COMPOSE))
    problems = guard.violations(defaults, {"NATS_URL": "nats://localhost:4222"})
    assert len(problems) == 1, f"الحارس لا يرى العطل المقيس: {problems}"
    assert "nats://sahool-nats:4222" in problems[0]

"""حارسٌ يموت وهو يطبع نجاحه — GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01.

الأعطال هنا **تُزرَع في حرّاس صناعيّين** يُكتَبون في `tmp_path` ويُشعَلون عمليّاتٍ
فرعيّة حقيقيّة تحت لغة C. والبديل — قراءة مصدر الحارس والتأكّد من وجود `reconfigure` —
كان سيقيس **نصّاً** لا **أثراً**: السطر قد يوجد بعد أوّل طباعة فلا ينفع، وقد يغيب عن
حارسٍ لا يطبع إلّا ASCII فلا يضرّ.

والحالة الفارقة ليست «هل يُبلِغ عن الميّت» بل **«هل يسكت عن الحيّ»**: حارسٌ يخرج بـ2
لأنّه يحتاج وسيطاً ليس عطلاً ترميزيّاً، وإدانتُه تُنتِج أساساً مُبالِغاً يُدرَّب قارئه
على تجاهله — وهو أشيع أعطال الحرّاس في هذا المستودع.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "guard_locale_survival_guard", ROOT / "scripts/ci/guard_locale_survival_guard.py"
)
gls = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(gls)


_DIES = """\
print("الحارس مرّ")
"""

_SURVIVES = """\
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")
print("الحارس مرّ")
"""

_FAILS_FOR_ANOTHER_REASON = """\
import sys

print("needs an argument", file=sys.stderr)
raise SystemExit(2)
"""


def _guard(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}_guard.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_an_encoding_death_is_reported(tmp_path: Path) -> None:
    """يحسب صحيحاً ثمّ يموت وهو يطبع نجاحه — وهذا بيت القصيد كلّه."""
    script = _guard(tmp_path, "dying", _DIES)

    deaths = gls.evaluate([script], gls.c_locale_env())

    assert deaths == [("dying_guard.py", "UnicodeEncodeError")]


def test_a_guard_that_reconfigures_its_console_is_not_reported(tmp_path: Path) -> None:
    script = _guard(tmp_path, "surviving", _SURVIVES)

    assert gls.evaluate([script], gls.c_locale_env()) == []


def test_a_nonzero_exit_for_another_reason_is_not_an_encoding_death(tmp_path: Path) -> None:
    """رمزُ الخروج يقول «فشل» ولا يقول **لماذا** — والفرق هو كلّ ما يُقاس هنا.

    حارسٌ يطلب وسيطاً أو قاعدةً يخرج بغير صفر على شجرةٍ سليمة. إدانتُه تخلط «عجز عن
    الطباعة» بـ«يحتاج تشغيلاً مختلفاً»، وتُنتِج قائمةً تُقرأ ديناً وهي ليست منه.
    """
    script = _guard(tmp_path, "needs_args", _FAILS_FOR_ANOTHER_REASON)

    assert gls.evaluate([script], gls.c_locale_env()) == []


def test_the_probe_strips_inherited_encoding_overrides(monkeypatch) -> None:
    """`PYTHONIOENCODING` موروثة تُبطِل التجربة **بصمت** فتُبلِغ نجاحاً لم يقع.

    ولا يكفي ضبط `LC_ALL`: المتغيّران يعملان من جهتين، وأحدهما يكفي لجعل المخرَج
    UTF-8 رغم لغة C. فتجربةٌ لا تعزل بيئتها تقيس البيئة لا الحارس.
    """
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    monkeypatch.setenv("PYTHONUTF8", "1")

    env = gls.c_locale_env()

    assert "PYTHONIOENCODING" not in env
    assert env["PYTHONUTF8"] == "0"
    assert env["LC_ALL"] == "C"


def test_an_inherited_override_would_have_hidden_a_real_death(tmp_path: Path) -> None:
    """البرهان المقابل: بنفس الحارس الميّت، بيئةٌ غير معزولة تُبلِغ سلامةً."""
    script = _guard(tmp_path, "dying", _DIES)
    leaky = dict(os.environ)
    leaky.update({"LC_ALL": "C", "LANG": "C", "PYTHONIOENCODING": "utf-8"})

    assert gls.evaluate([script], leaky) == []
    assert gls.evaluate([script], gls.c_locale_env()) != []


def test_the_guard_never_probes_itself() -> None:
    """إشعالُ النفس تعشيشٌ بلا قاع — وقع في أوّل تشغيل: ثلاث دقائق لجولةِ دقيقة."""
    names = {p.name for p in gls.guard_scripts()}

    assert "guard_locale_survival_guard.py" not in names
    assert names, "جردٌ فارغ يمرّ دائماً — وهو صمتٌ يُقرأ خضرةً"


def test_the_inventory_covers_every_guard_but_itself() -> None:
    on_disk = {p.name for p in (ROOT / "scripts/ci").glob("*_guard.py")}

    assert {p.name for p in gls.guard_scripts()} == on_disk - {"guard_locale_survival_guard.py"}


_DIES_ON_IMPORT = """\
import a_module_that_does_not_exist  # noqa: F401

print("never reached")
"""


def test_a_guard_that_dies_on_import_is_counted_unmeasured(tmp_path: Path) -> None:
    """مات قبل أوّل طباعة ⇒ مرورُه ليس دليلاً، ويُعلَن عدده بدل أن يُقرأ خضرةً.

    يقع فعلاً حين تُوضَع البوّابة في وظيفةٍ بلا تبعيّات الجناح — وهو ما جعل
    `guard_mutation_guard --run` يُبلِغ مرّةً ثمانية عشر «إخفاقاً» صحيحاً بسببٍ خاطئ.
    """
    script = _guard(tmp_path, "importless", _DIES_ON_IMPORT)

    deaths, blind = gls.sweep([script], gls.c_locale_env())

    assert deaths == [], "استيرادٌ ناقص ليس موتاً ترميزيّاً"
    assert blind == ["importless_guard.py"]


def test_a_guard_that_actually_ran_is_not_counted_unmeasured(tmp_path: Path) -> None:
    script = _guard(tmp_path, "surviving", _SURVIVES)

    assert gls.sweep([script], gls.c_locale_env()) == ([], [])

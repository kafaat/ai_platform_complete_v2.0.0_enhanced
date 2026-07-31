"""حارس الموضع القانونيّ لمهارات supervisor-agent — SUPERVISOR-ROOT-SKILLS-DEAD-CODE-01.

كانت الخدمة تحمل **نسختين** من كلّ مهارة: واحدة في جذرها وأخرى في ``skills/``.
النسخ الجذريّة كانت **ميتة ومتباعدة معاً** — وهو أسوأ من التكرار الصرف:

  advisory_skill        ١٣٧ سطراً مقابل ٢٤٨  ⇒ ١٢٣ سطراً مختلفاً
  crop_model_skill      ١٦٠ مقابل ١٦٥        ⇒ ٩
  market_skill          ١١١ مقابل ٩٦         ⇒ ١٧
  remote_sensing_skill  ١٧٦ مقابل ١٧٦        ⇒ ٢

``main.py`` يستورد ``skills.*`` حصراً، وentrypoint الحاوية ``uvicorn main:app``.
فقارئ مستقبليّ قد يُعدّل النسخة الخطأ ويظنّ أنّه غيّر السلوك — والفرق البالغ ١٢٣
سطراً في ``advisory_skill`` فرق **قدرة** لا أسلوب.

حُذِفت الأربع (٥٨٤ سطراً) بعد إثبات صفر مستهلك: صفر استيراد جذريّ في الشجرة كلّها،
صفر ``__main__``، وapp mounting يمرّ عبر ``skills/`` وحدها. هذا الحارس يمنع عودتها
— فالموضع القانونيّ الوحيد هو ``skills/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "services" / "supervisor-agent"
SKILLS_PKG = SUPERVISOR / "skills"


def test_no_skill_module_at_service_root():
    """الموضع القانونيّ ``skills/`` — لا وحدة ``*_skill.py`` في جذر الخدمة."""
    strays = sorted(p.name for p in SUPERVISOR.glob("*_skill.py"))
    assert not strays, (
        f"وحدات مهارات عادت إلى جذر supervisor-agent: {strays}. "
        f"الموضع القانونيّ هو skills/ — main.py يستورد skills.* حصراً، "
        "ونسخة الجذر ستكون ميتة (ومتباعدة صامتاً كما حدث سابقاً)."
    )


def test_canonical_skills_package_is_intact():
    """الأربع الحيّة موجودة فعلاً — الحذف أزال الميت لا الحيّ."""
    expected = {
        "advisory_skill.py",
        "crop_model_skill.py",
        "market_skill.py",
        "remote_sensing_skill.py",
    }
    present = {p.name for p in SKILLS_PKG.glob("*_skill.py")}
    missing = expected - present
    assert not missing, f"مهارات مفقودة من الموضع القانونيّ skills/: {sorted(missing)}"


def test_main_imports_only_the_canonical_package():
    """``main.py`` يستورد ``skills.*`` — لا استيراد جذريّ عارٍ يُعيد إحياء النمط."""
    src = (SUPERVISOR / "main.py").read_text(encoding="utf-8")
    for name in ("advisory_skill", "crop_model_skill", "market_skill", "remote_sensing_skill"):
        assert f"from skills.{name} import" in src, f"main.py لا يستورد skills.{name}"
        for bare in (f"from {name} import", f"import {name}\n"):
            assert bare not in src, f"main.py يستورد {name} من الجذر — النمط الميت عاد"


def test_no_bare_root_import_anywhere_in_tree():
    """صفر استيراد جذريّ عبر الشجرة — الشرط الذي بُني عليه الحذف يبقى محروساً."""
    names = ("advisory_skill", "crop_model_skill", "market_skill", "remote_sensing_skill")
    offenders: list[str] = []
    for py in ROOT.rglob("*.py"):
        if "__pycache__" in py.parts or ".venv" in py.parts:
            continue
        if py.resolve() == Path(__file__).resolve():
            continue  # هذا الملفّ يذكر الأسماء نصّاً بالتصميم
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith(("import ", "from ")):
                continue
            for n in names:
                if s.startswith(f"from {n} ") or s == f"import {n}":
                    offenders.append(f"{py.relative_to(ROOT).as_posix()}: {s}")
    assert not offenders, f"استيراد جذريّ عاد: {offenders}"

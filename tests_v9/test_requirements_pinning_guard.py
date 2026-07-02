"""حارس تثبيت التبعيّات على المسار الحرج (SEC-6 — النطاق الآمن).

الخلفيّة: ~157 مواصفة تبعيّة عبر الريبو تستخدم مدَيات `>=`/غير مثبّتة ⇒ خطر
انحراف البناء (build drift): تثبيتان في وقتين مختلفين قد يجلبان إصدارات مختلفة،
فيختلف السلوك بين التطوير والإنتاج، وقد تتسلّل ترقية ثانويّة بثغرة دون أن يمسّها
أحد (بالضبط ما حصل مع python-multipart 0.0.27؛ راجع CLAUDE.md).

قفلٌ كاملٌ فوريّ لكلّ الملفّات خطر: قد يُظهر تعارضات حقيقيّة تكسر التثبيت عبر
خدمات كثيرة ويستوجب التراجع. لذا SEC-6 يقدّم زيادة آمنة **غير كاسرة** + خطّة
مرحليّة موثّقة (`docs/security/dependency_locking_plan.md`).

هذا الحارس **مسح ملفّات صرف** (لا يستورد fastapi ولا يرفع خدمة) و**سقّاطة
(ratchet)**: أخضر اليوم، ويمنع الانحدار فقط. يفرض ثلاثة ثوابت على الملفّات
الأربعة التي تحرسها بوّابة pip-audit في CI (المسار الحرج — راجع CLAUDE.md):

  1. لا يُفكّ تثبيت حزمة مثبّتة اليوم بـ`==` (أرضيّة السقّاطة).
  2. لا يزيد عدد الحزم غير المثبّتة في أيّ ملفّ عن خطّ الأساس الموثّق
     (يُسمح بالنقصان — أي بتثبيت المزيد — لا بالزيادة).
  3. إطار العمل النواة (fastapi/uvicorn/pydantic) مثبّت على **نفس** الإصدار
     عبر الملفّات الأربعة (يمنع انزلاق إصدار الإطار على المسار الحرج).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# الملفّات الأربعة التي تحجب pip-audit الدمج عليها (المسار الحرج، CLAUDE.md).
CRITICAL_PATH = (
    "services/sahool-platform/api/requirements.txt",
    "services/auth/requirements.txt",
    "services/guardrails-engine/requirements.txt",
    "requirements_real.txt",
)

# خطّ الأساس (2026-07-02): الحزم المثبّتة اليوم بـ`==` في كلّ ملفّ. أرضيّة
# السقّاطة — فكّ تثبيت أيّ منها يُفشل الحارس. عند تثبيت المزيد لاحقاً (تنفيذ
# الخطّة المرحليّة) وسّع هذه المجموعات ليَقفل السقّاطة على المكسب الجديد.
BASELINE_PINNED = {
    "services/sahool-platform/api/requirements.txt": {
        "defusedxml", "fastapi", "httpx", "nats-py", "numpy", "pydantic",
        "pyjwt", "pyotp", "pyshp", "python-multipart", "pyyaml", "redis",
        "scipy", "uvicorn",
    },
    "services/auth/requirements.txt": {"fastapi", "pydantic", "uvicorn"},
    "services/guardrails-engine/requirements.txt": {"fastapi", "pydantic", "uvicorn"},
    "requirements_real.txt": {"fastapi", "pydantic", "uvicorn"},
}

# خطّ الأساس: أقصى عدد مسموح من الحزم غير المثبّتة لكلّ ملفّ. السقّاطة تمنع
# الزيادة (تبعيّة مدَى جديدة) وتُكافئ النقصان (تثبيت). خفّض هذه الأرقام عند
# تنفيذ الخطّة المرحليّة كي لا يعود الانحراف.
BASELINE_UNPINNED_MAX = {
    "services/sahool-platform/api/requirements.txt": 2,
    "services/auth/requirements.txt": 8,
    "services/guardrails-engine/requirements.txt": 8,
    "requirements_real.txt": 12,
}

# إطار العمل النواة — يجب أن يكون مثبّتاً على نفس الإصدار عبر المسار الحرج.
CORE_FRAMEWORK = ("fastapi", "uvicorn", "pydantic")


def _pkg_name(spec: str) -> str:
    """اسم الحزمة المُطبَّع من مواصفة (يُسقط الـextras والقيود)."""
    m = re.match(r"^([A-Za-z0-9_.\-]+)", spec)
    return m.group(1).lower() if m else spec.lower()


def _parse(path: str):
    """يُرجع (pinned: dict name->version, unpinned: list[str]) لملفّ."""
    pinned: dict[str, str] = {}
    unpinned: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            spec = line.split("#", 1)[0].strip()
            if not spec or spec.startswith("-"):
                continue
            name = _pkg_name(spec)
            m = re.search(r"==\s*([A-Za-z0-9_.\-]+)", spec)
            if m:
                pinned[name] = m.group(1)
            else:
                unpinned.append(spec)
    return pinned, unpinned


@pytest.mark.unit
def test_critical_path_files_exist():
    for rel in CRITICAL_PATH:
        assert os.path.isfile(os.path.join(ROOT, rel)), (
            f"ملفّ المسار الحرج مفقود: {rel} — بوّابة pip-audit في CI تعتمده."
        )


@pytest.mark.unit
def test_baseline_pinned_stay_pinned():
    """أرضيّة السقّاطة: لا انحدار — كلّ حزمة مثبّتة اليوم تبقى مثبّتة بـ`==`."""
    problems = []
    for rel, expected in BASELINE_PINNED.items():
        pinned, _ = _parse(os.path.join(ROOT, rel))
        for name in sorted(expected):
            if name not in pinned:
                problems.append(
                    f"{rel}: '{name}' كان مثبّتاً بـ`==` وفُكّ تثبيته — "
                    f"يعيد خطر انحراف البناء على المسار الحرج."
                )
    assert not problems, "انحدار تثبيت على المسار الحرج:\n  " + "\n  ".join(problems)


@pytest.mark.unit
def test_unpinned_count_does_not_grow():
    """سقّاطة: عدد الحزم غير المثبّتة لكلّ ملفّ لا يتجاوز خطّ الأساس."""
    problems = []
    for rel, max_allowed in BASELINE_UNPINNED_MAX.items():
        _, unpinned = _parse(os.path.join(ROOT, rel))
        if len(unpinned) > max_allowed:
            problems.append(
                f"{rel}: {len(unpinned)} حزمة غير مثبّتة > الأساس {max_allowed}. "
                f"غير المثبّتة: {unpinned}. ثبّت الجديد بـ`==` أو حدّث الأساس عمداً."
            )
    assert not problems, "زاد انحراف التبعيّات:\n  " + "\n  ".join(problems)


@pytest.mark.unit
def test_core_framework_version_consistent_across_critical_path():
    """إطار العمل النواة مثبّت على نفس الإصدار عبر الملفّات الأربعة."""
    versions: dict[str, dict[str, str]] = {pkg: {} for pkg in CORE_FRAMEWORK}
    for rel in CRITICAL_PATH:
        pinned, _ = _parse(os.path.join(ROOT, rel))
        for pkg in CORE_FRAMEWORK:
            if pkg in pinned:
                versions[pkg][rel] = pinned[pkg]
    problems = []
    for pkg, by_file in versions.items():
        distinct = set(by_file.values())
        if len(distinct) > 1:
            problems.append(f"{pkg}: إصدارات متضاربة على المسار الحرج {by_file}")
    assert not problems, (
        "انزلاق إصدار إطار العمل النواة على المسار الحرج:\n  "
        + "\n  ".join(problems)
    )

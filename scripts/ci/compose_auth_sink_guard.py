#!/usr/bin/env python3
"""سرُّ استيثاقٍ لا يصل فارغاً — `SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01`.

**الخاصّيّةُ المفروضة هنا غير التي يفرضها `compose_no_default_secrets_guard.py`.**
ذاك يقول «لا سرَّ افتراضيّ منشور»، وهذا يقول «سرٌّ يحكم تفعيلَ استيثاق خادم لا
يجوز أن تصل قيمتُه فارغةً». والعقدان يتقاطعان ولا يتطابقان: `${VAR:-}` الفارغة
تُرضي ذاك وتنتهك هذا، والقيمةُ الحرفيّة تنتهك الاثنين **لسببين مختلفين**.

وهو تطبيقٌ مباشر لـ`GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`: وجودُ `?` في
التعبير ليس شاهداً على fail-closed. الفرق القانونيّ مقيسٌ بـ`docker compose
config`:

  ``${V?e}``   ⇒ موجودٌ — ويقبل الفارغ
  ``${V:?e}``  ⇒ موجودٌ **و**غير فارغ

فالمفروض إثباتُ `required AND non-empty`، لا «المتغيّر موجود» ولا «التعبير فيه
علامة استفهام».

**والصيغةُ المقبولة واحدة: ``${VAR:?…}``.** ولا تُقبَل قيمةٌ حرفيّة ولو كانت غير
فارغة — فهي تُرضي «غير فارغ» وتنتهك «لا سرَّ منشور»، وتمريرُها كان سيجعل الحارس
يُبارِك سرّاً مكشوفاً في مكدّسٍ إنتاجيّ. تُقبَل في مكدّسِ اختبارٍ باستثناءٍ
**مقيَّدٍ بالملفّ وبالخدمة** ومملوكٍ بعقد الاختبار — لا بقاعدةٍ عامّة، ولا على
مكدّسٍ إنتاجيّ مهما أعلن المدخلُ عن نفسه.

**والنطاق سجلٌّ صريحٌ بالاسم، لا نمط `.*API_KEY`.** بعض متغيّرات المفاتيح اعتمادُ
عميلٍ اختياريّ لا مفتاحٌ يحمي خادماً، وإلزامُها عالميّاً يكسر مكدّسات تعمل بلا
مزوّدٍ خارجيّ بحقّ. يُوسَّع بمصرفٍ **مقيسٍ** واحدٍ في المرّة.

النطاق من `compose_surface.py` — مصدرُ اكتشافٍ واحد، ومعه شهودُ
`GUARD-SCOPE-COMPLETENESS` الخمسة.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose_surface import ROOT, compose_files, discovery_witness  # noqa: E402

SINKS_DOC = ROOT / "docs" / "architecture" / "compose_auth_sinks.json"

#: `${NAME<op><arg>}` — العاملُ ملتقَطٌ كاملاً لأنّ النقطتين هي كلّ الفرق.
_INTERP = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-|:\?|:\+|-|\?|\+)?([^}]*)\}")

#: صيغةُ الإسناد في مقطع `environment:` — خريطةً (`K: v`) أو قائمةً (`- K=v`).
_ASSIGN = re.compile(r"^\s*(?:-\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*?)\s*$")

#: القيمةُ المقبولة وحدها: استيفاءٌ واحد بعامل `:?` يشغل القيمة كلَّها.
_ACCEPTED = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*):\?[^}]*\}$")


def _doc() -> dict:
    return json.loads(SINKS_DOC.read_text(encoding="utf-8"))


def _sinks() -> dict[str, dict]:
    return _doc()["sinks"]


def _exceptions() -> dict[str, dict]:
    return _doc().get("exceptions", {}).get("entries", {})


def _production_files() -> set[str]:
    return set(_doc().get("production_stacks", {}).get("files", []))


def _unquote(value: str) -> str:
    text = value.strip()
    for quote in ('"', "'"):
        if len(text) >= 2 and text.startswith(quote) and text.endswith(quote):
            return text[1:-1]
    return text


def _why_rejected(value: str) -> str:
    """سببُ الرفض بلغة الخاصّيّة — رسالةٌ تُعلِّم بدل أن تُدين."""
    text = _unquote(value)
    if not text:
        return "قيمةٌ خالية"
    if "${" not in text:
        return (
            "قيمةٌ حرفيّة — غيرُ فارغة لكنّها **سرٌّ منشور**؛ الاستثناء التجريبيّ "
            "يُمنَح بالملفّ وبالخدمة، لا بقاعدةٍ عامّة"
        )
    if re.search(r"\$\{[A-Za-z_][A-Za-z0-9_]*\?", text):
        return "`?` بلا نقطتين تفرض **الوجود** وتقبل الفارغ — المطلوب `:?`"
    if re.search(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-\s*\}", text):
        return "`:-` فارغة تُمرّر الخالي دائماً"
    if re.search(r"\$\{[A-Za-z_][A-Za-z0-9_]*-", text):
        return "`-` بلا نقطتين: ضبطٌ فارغ يبقى خالياً"
    if re.search(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", text):
        return "استيفاءٌ عارٍ: غير المضبوط والفارغ كلاهما يصل خالياً"
    return "لا يُثبِت `required AND non-empty`"


def scanned_files() -> list[str]:
    """الملفّاتُ التي مرّ عليها الفحص فعلاً — الشاهد ② مُصنَّعاً لا موصوفاً.

    ``findings()`` تُرجِع الانتهاكات، وملفٌّ مطابقٌ لا يُنتِج شيئاً — فلا يمكن أن
    يُقاس من مخرجاتها أنّه فُحِص. وهذه تفصل «لم يجد» عن «لم ينظر»، وهما نتيجتان
    متطابقتان في الخضرة ومتناقضتان في المعنى.
    """
    return [str(p.relative_to(ROOT)) for p in _scan_surface()]


def _scan_surface() -> list[Path]:
    """سطحُ الفحص — نقطةٌ واحدة يمرّ منها الفاحص والشاهد معاً."""
    return list(compose_files())


def findings() -> list[tuple[str, str]]:
    """(مفتاح، رسالة) لكلّ مصرفٍ لا يُثبِت `required AND non-empty` — بلا ترشيح."""
    sinks = _sinks()
    out: list[tuple[str, str]] = []
    for path in _scan_surface():
        rel = str(path.relative_to(ROOT))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            match = _ASSIGN.match(stripped)
            if not match:
                continue
            name, value = match.group(1), match.group(2)
            spec = sinks.get(name)
            if spec is None:
                continue
            # التعليقُ اللاحق ليس من القيمة — `${V}  # ملاحظة` قيمتُها `${V}`.
            value = re.sub(r"\s+#.*$", "", value)
            if _ACCEPTED.match(_unquote(value)):
                continue
            out.append(
                (
                    f"{rel}::{name}",
                    f"{rel}:{number}: {name} — {_why_rejected(value)}. "
                    f"خدمة `{spec['service']}` تعتمد عليه في تفعيل الاستيثاق، "
                    f"فالمقبول `{spec['allowed_form']}` وحدها",
                )
            )
    return out


def violations() -> list[str]:
    """الانتهاكات بعد ترشيح الاستثناءات المقيَّدة بالملفّ والخدمة."""
    allowed = _exceptions()
    return [message for key, message in findings() if key not in allowed]


def exception_defects() -> list[str]:
    """استثناءٌ ناقصُ العقد، أو ممنوحٌ لمكدّسٍ إنتاجيّ، أو بائتٌ بلا انتهاك."""
    problems: list[str] = []
    live = {key for key, _ in findings()}
    production = _production_files()
    for key, entry in sorted(_exceptions().items()):
        for field in ("service", "reason", "owner", "expires_on"):
            if not str(entry.get(field, "")).strip():
                problems.append(f"استثناءٌ بلا {field}: {key}")
        if entry.get("non_production") is not True:
            problems.append(
                f"استثناءٌ بلا إقرار `non_production`: {key} — الاستثناء التجريبيّ لا يُعمَّم"
            )
        if key.split("::", 1)[0] in production:
            problems.append(f"استثناءٌ على مكدّسٍ إنتاجيّ: {key} — مرفوضٌ مهما أعلن المدخلُ عن نفسه")
        if "::" not in key:
            problems.append(f"استثناءٌ غير مقيَّدٍ بالملفّ والمتغيّر: {key} — إعفاءُ جملة")
        if key not in live:
            problems.append(f"استثناءٌ بائت (لا انتهاك يقابله): {key} — احذفه، القائمة تتقلّص")
    return problems


def unmeasured_sinks() -> list[str]:
    """مصرفٌ مُعلَنٌ لا يظهر على السطح — **يحجب**.

    اختفاءُ مصرفٍ مُسجَّل بلا تحديث العقد هو كيف يصير الحارس حارسَ لا شيء: يبقى
    أخضر لأنّه لا يجد ما يفحص. فيُحجَب حتّى يُحسَم — أزيلت الخدمة؟ فأزِل المصرف
    صراحةً.
    """
    live: set[str] = set()
    for path in _scan_surface():
        text = path.read_text(encoding="utf-8")
        live |= {name for name in _sinks() if name in text}
    return sorted(set(_sinks()) - live)


def main() -> int:
    witness = discovery_witness()
    problems = violations()
    problems += exception_defects()
    for name in unmeasured_sinks():
        problems.append(
            f"مصرفٌ مُعلَنٌ لا يظهر على السطح: {name} — حارسٌ بلا ما يفحص يبقى أخضر بلا معنى؛ "
            "أزِله من العقد صراحةً أو أعِد الخدمة"
        )

    if problems:
        print("compose_auth_sink_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print(f"\n  السطح المفحوص ({len(witness['discovered_paths'])} ملفّاً):")
        for rel in witness["discovered_paths"]:
            print(f"    · {rel}")
        return 1

    print(
        f"compose_auth_sink_guard: PASS "
        f"({len(witness['discovered_paths'])} ملفّاً على السطح · "
        f"{len(_sinks())} مصرفاً مُعلَناً · {len(_exceptions())} استثناءً مقيَّداً · "
        f"المصدر: {witness['universe_source']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

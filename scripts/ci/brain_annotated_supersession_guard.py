#!/usr/bin/env python3
"""مفرداتُ وسم السجلّ إعلانٌ — هذا الحارسُ يجعلها **مقيسة**.

`ANNOTATED-SUPERSESSION-CLOSES-A-GAP-WITHOUT-A-WITNESS-01`

أدخل #1031 مفرداتِ وسمٍ تحسم العناوينَ المكرّرة: `<!-- gap-registry: current -->`
و`historical` (ومعهما `alias` · `policy` · `adjudicated`). وهي **علاجٌ صحيح** — حفظت
نصَّ الاكتشاف الأصليَّ بدل محوه، وأبقت الخلافَ ظاهراً في `historical_state_variations`.
لكنّها دخلت **بلا كلفة**: مقيسٌ على `c3ebd6a7` أنّ قارئاً واحداً يقرؤها
(`gap_registry_measure.py`)، واختباراً واحداً يفحصها، و**فحصُه شكليٌّ بحتاً**:
`current` واحدةٌ لكلّ مجموعة · موضعُ التعليق سطراً تالياً للعنوان · تعليقٌ مجهول
يُبلَّغ. ولا شيءَ يربط `current` بكونها **فعلاً** المتأخّرة.

فبقي المسارُ الآتي أخضرَ بالكامل: تأخذ فجوةً حالتُها `open`، تنسخ عنوانَها، تضع
النسخةَ الجديدة `fixed` وتسمها `current`، وتسم الأصلَ `historical` — فتختفي الفجوةُ
المفتوحةُ من كلّ عدٍّ يُقرأ، **بلا حارسٍ يحمرّ**. و`README` السجلّ نفسُه يكتب القاعدةَ
المانعة نثراً للبشر: «لا يُختار المدخل الحالي لمجرّد موضعه في الملفّ» — وهي قاعدةٌ
تُقرأ ولا تُنفَّذ.

**والقياسُ report-only يضاعف الفجوة لا يسدّها:** وظيفةُ `gap-registry-report` تحمل
`continue-on-error: true` (وهي الثلاثيّةُ الوحيدةُ المستبعَدة من سطح الحجب على هذا
الرأس، مقيسةً ٣٠٣ ⇒ ٣٠٢). فحتّى التناقضُ الصريح — معرِّفٌ واحدٌ بحالتين بلا وسمِ
تاريخ — يُطبَع ولا يحجب.

## البندان — وكلاهما عند أرضيّته المقيسة اليوم

**① التناقضُ غيرُ الموسوم يحجب.** `contradictory_section_id_count = 0` على
`c3ebd6a7` (كان ١ قبل #1031، وحُسِم بالوسم لا بالحذف). أرضيّةٌ عند الصفر: راتشِتٌ
لا يصعد.

**② الخلافةُ المُغلِقة تدفع شاهداً.** مجموعةٌ موسومةٌ فيها مدخلٌ `historical` حالتُه
`open` ومدخلٌ `current` حالتُه `fixed`/`verified` ⇒ نصُّ `current` **يجب** أن يستشهد
بمسارٍ موجودٍ في الشجرة يصلح شاهداً. المقيسُ اليوم: مجموعةٌ واحدة
(`GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01`) وهي تستشهد بـ
`tests_v9/test_guardrail_flags_reach_every_image.py` — فالبندُ يمرّ على الشجرة
القائمة، ولا يُدخَل حاجباً يطلب عملاً لم يُعمَل.

**ولِمَ المسارُ الموجود مرساةٌ وليس إعلاناً ثانياً:** وجودُ الملفّ حقيقةٌ عن الشجرة لا
عن نيّة كاتبه. ومن يلفّق إغلاقاً يلزمه أن يزرع ملفَّ شاهدٍ حقيقيّاً — وعندها تتولّاه
بوّاباتُ التسجيل والعلامات (`arch_test_ci_coverage` · `marker_coverage`) فتطالبه
بتشغيله. الكلفةُ لا تصير صفراً في أيّ فرع.

## الحالاتُ التي **يجب** أن تمرّ — فحصُ «حارسٍ لا يقبل حالةً صادقة»

هذا الصنفُ أُغلق في #1026 (ربطٌ جامعٌ لا منفرد)، ويُفحَص هنا سلفاً:

- `historical=fixed` · `current=open` ⇒ **إعادةُ فتح**، لا خلافةَ مُغلِقة ⇒ تمرّ بلا
  شاهد. مطالبتُها بشاهدِ إغلاق كانت ستجعل إعادةَ الفتح مستحيلةً بعد الوسم.
- `historical=open` · `current=open` ⇒ تمرّ.
- مجموعةٌ موسومةٌ بلا سطرِ حالةٍ أصلاً (١٣ من ١٤ على هذا الرأس) ⇒ تمرّ: لا حالةَ
  تُخفى.
- عناوينُ مكرّرةٌ غيرُ موسومة ⇒ خارجَ النطاق؛ يبلّغها القياسُ بوصفها غيرَ محسومة.

## ما لا يدّعيه

لا يحكم على صحّة الإغلاق نفسِه، ولا يقرأ تاريخَ git (استنساخُ CI بعمق ١ — الصنفُ
المسجَّل في `CLAUDE.md` §٣.٢٥د)، ولا يُرقّي قياسَ `gap_registry_measure` إلى بوّابة:
عددُ غيرِ المصنَّف يبقى إرشاديّاً كما نصّ #1031. يقيس بندَين اثنين لا ثالثَ لهما.

يقرأ من **محرّك القياس نفسِه** (`gap_registry_measure.measure`) لا من مُحلِّلٍ ثانٍ —
نموذجان لسجلٍّ واحد كانا سينحرفان، وهو عطلٌ مسجَّلٌ في هذا المستودع.

يعمل بلا pytest — نفس نمط `brain_duplicate_gap_identity_guard`.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. تحت `LC_ALL=C` يحسب صحيحاً ثمّ يموت وهو يطبع نجاحه
# ⇒ خروجٌ بـ1 يُقرأ «الحارس يحجب» وهو قد مرّ. **عند التحميل لا داخل `main()`.**
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"
MEASURE = ROOT / "scripts/ci/gap_registry_measure.py"

CLOSING = ("fixed", "verified")

# مسارٌ مُستشهَدٌ به: إمّا داخل `code span`، وإمّا هدفُ رابط Markdown. الحدُّ الأدنى
# مقطعٌ واحدٌ ثمّ امتداد — فلا يُلتقَط `config/` مجرّداً ولا جملةٌ فيها شرطة مائلة.
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
_PATHLIKE = re.compile(r"^[\w./-]+/[\w.-]+\.[A-Za-z0-9]+$")
# ذكرُ سكربتِ حارسٍ في نصّ workflow — بلا مُحلِّل YAML (انظر `_wired_guards`).
_GUARD_MENTION = re.compile(r"\bscripts/ci/[\w./-]+\.(?:py|sh)\b")


def _load_measure():
    """محرّكُ القياس نفسُه — لا مُحلِّلٌ ثانٍ للسجلّ."""
    spec = importlib.util.spec_from_file_location("gap_registry_measure", MEASURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cited_paths(text: str) -> set[str]:
    """المساراتُ المذكورةُ في نصٍّ، مُطبَّعةً من بادئات `../` النسبيّة في السجلّ."""
    found: set[str] = set()
    for raw in _CODE_SPAN.findall(text) + _LINK_TARGET.findall(text):
        candidate = raw.strip().split("#", 1)[0].split(":", 1)[0]
        while candidate.startswith("../"):
            candidate = candidate[3:]
        if _PATHLIKE.fullmatch(candidate):
            found.add(candidate)
    return found


def is_witness(path: str, root: Path, wired_guards: set[str]) -> bool:
    """شاهدٌ **مقيس**: ملفُّ اختبارٍ فيه دالّةُ اختبارٍ واحدة على الأقلّ، أو حارسٌ
    في `scripts/ci/` تستدعيه workflow فعلاً.

    والاشتراطُ على المحتوى مقصود: ملفٌّ فارغٌ باسمٍ صحيح كان سيجعل ثمنَ الإغلاق
    `touch` — أي صفراً بخطوةٍ إضافيّة.
    """
    target = root / path
    if not target.is_file():
        return False
    name = target.name
    if name.startswith("test_") or name.endswith("_test.py"):
        try:
            return "def test_" in target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    return path in wired_guards


def _section_text(lines: list[str], heading_line: int) -> str:
    """متنُ المدخل: من عنوانه إلى العنوان التالي. `heading_line` مُرقَّمٌ من ١."""
    start = heading_line - 1
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _wired_guards() -> set[str]:
    """`scripts/ci/*` المذكورةُ في أيّ workflow — بمكتبة بايثون القياسيّة وحدها.

    GUARD-IMPORTS-A-DEPENDENCY-ITS-JOB-NEVER-INSTALLS-01. كان هذا يستورد
    `guard_catalogue.discover_invocation_sites()` لأنّه «القارئُ القائم»، وهو الاختيارُ
    الصحيح مبدئيّاً وكان **خاطئاً بالقياس**: `guard_catalogue` يستورد `PyYAML`،
    ووظيفةُ `no-report-only-change` لا تُثبِّت تبعيّةً واحدة — حرّاسُ الدماغ الخمسةُ
    فيها بايثون قياسيّةٌ صرفة. فسقط الحارسُ بـ`ModuleNotFoundError` في أوّل تشغيلٍ
    على CI، بينما مرّ `preflight --fast` أخضرَ لأنّ `PyYAML` مُثبَّتةٌ محلّيّاً.
    **أخضرُ محلّيٌّ قِيس في كونٍ غيرِ المنشور** — وهو الصنفُ الذي يسجّله هذا المستودع
    باسم «استيرادٌ يعمل في الاختبار وينكسر في الحاوية».

    والعلاجُ ليس تثبيتَ `PyYAML` في الوظيفة: ذلك يوسّع سطحَ تبعيّةِ وظيفةٍ بقيت
    بلا تبعيّاتٍ عمداً، ولأجل **سؤالٍ لا يحتاج مُحلِّل YAML أصلاً**.

    **وحدُّ الدعوى ضاق بصدق:** «مذكورٌ في نصّ workflow» لا «تستدعيه وظيفةٌ بعينها».
    الفرقُ لا يخدم مُلفِّقاً: من يستشهد بحارسٍ ليدفع ثمنَ إغلاق، فالمطلوبُ منه أن
    يكون الحارسُ موجوداً في الشجرة **و**مذكوراً في CI؛ وأيُّهما غاب رُفِض. ونسبةُ
    الاستدعاء إلى وظيفةٍ بعينها تخصّ الكتالوجَ وسطحَ الحجب، لا هذا السؤال.
    """
    workflows = ROOT / ".github/workflows"
    if not workflows.is_dir():
        return set()
    mentioned: set[str] = set()
    for path in sorted(workflows.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        mentioned.update(_GUARD_MENTION.findall(text))
    return mentioned


def findings(text: str, root: Path, wired_guards: set[str], measure) -> list[str]:
    """دالّةٌ نقيّة — تُختبَر بنصٍّ في الذاكرة بلا ملفّات ولا شجرة."""
    report = measure(text)
    lines = text.splitlines()
    out: list[str] = []

    # ① التناقضُ غيرُ الموسوم — أرضيّةٌ عند الصفر، راتشِتٌ لا يصعد.
    for gap_id in sorted(report["contradictory_sections"]):
        states = report["contradictory_sections"][gap_id]
        seen = sorted({s["state"] for s in states if s.get("state")})
        out.append(
            f"{gap_id}: معرِّفٌ واحدٌ بحالتين ({'/'.join(seen)}) بلا وسمِ تاريخ — "
            "إمّا أن تُحسَم بـ`current`/`historical`، وإمّا أن تُوحَّد الحالة"
        )

    # ② الخلافةُ المُغلِقة تدفع شاهداً.
    for gap_id in sorted(report["historical_state_variations"]):
        entries = report["historical_state_variations"][gap_id]
        superseded = [
            e for e in entries if e.get("entry_role") == "historical" and e.get("state") == "open"
        ]
        current = next((e for e in entries if e.get("entry_role") == "current"), None)
        if not superseded or current is None or current.get("state") not in CLOSING:
            continue  # إعادةُ فتحٍ أو بقاءٌ مفتوحاً — لا خلافةَ مُغلِقة، ولا شاهدَ يُطلَب.
        body = _section_text(lines, current["heading_line"])
        witnesses = sorted(p for p in cited_paths(body) if is_witness(p, root, wired_guards))
        if not witnesses:
            out.append(
                f"{gap_id}: مدخلٌ `current` يُغلِق ({current['state']}) ما يبقى "
                f"`historical` مفتوحاً (السطر {current['heading_line']}) بلا شاهدٍ "
                "مُستشهَدٍ به موجودٍ في الشجرة — الوسمُ وحدَه لا يُغلِق فجوة"
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args()

    if not args.registry.is_file():
        print(f"سجلُّ الفجوات غير موجود: {args.registry}", file=sys.stderr)
        return 1

    measure = _load_measure().measure
    problems = findings(args.registry.read_text(encoding="utf-8"), ROOT, _wired_guards(), measure)
    if problems:
        print("brain_annotated_supersession_guard: وسمٌ يُغلِق بلا ثمن", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("brain_annotated_supersession_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

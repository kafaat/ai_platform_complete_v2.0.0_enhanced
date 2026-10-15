#!/usr/bin/env python3
"""يمسك الفشل الصامت الذي يتركه دمج `union` — `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`.

`merge=union` يحلّ تعارض الملفّات الإلحاقيّة بضمّ سطور الجانبين بدل ترك العلامات.
وهو صحيح حين يُضيف كلّ جانب **مدخلاً مختلفاً**. لكن حين يُحرّر الجانبان **نفس السطر**
— وهو بالضبط ما يحدث حين تُحدّث جلستان حالة الفجوة نفسها — يُبقي union الاثنين
و**يخرج بـ0**:

    ## GAP-A — هبطت على main في abc1234
    ## GAP-A — مُغلقة بالجلسة الأخرى        ← حالتان متناقضتان، وgit يقول «نجح»

مقيس في مستودع مؤقّت، لا مفترَض. فالفشل صامت: لا علامة تعارض يمسكها
`conflict_marker_guard`، ولا خطأ نحويّ، ولا اختبار يسقط — فقط سجلّ يقول شيئين
متناقضين عن الفجوة نفسها. ولهذا يسبق هذا الحارس تفعيل union، لا يتبعه.

**والتصميم صُحِّح بالقياس مرّتين قبل أن يُكتَب:**

① **الهويّة لا النصّ.** مقارنة عناوين حرفيّاً تفوت الحالة الخطرة تماماً: العنوانان
   أعلاه مختلفان نصّاً، متطابقان هويّةً. المقارنة على **معرّف الفجوة** وحده.

② **والتلاصق لا التكرار.** أوّل تصميم كان «معرّف يتكرّر ⇒ فشل». تشغيله على الشجرة
   أعطى **١١** إصابة، **عشرٌ منها شرعيّة**: السجلّ يحتفظ عمداً بسلاسل تاريخيّة
   (`SILENT-EXCEPTION-HANDLERS-11-01` ثلاث مرّات بثلاث حالات مؤرَّخة،
   و`SPECTRAL-STALE-DECISION-LINKED-CLAIMS-01` بمدخل موسوم «أُبقي للمصدر»). حارسٌ
   يرفع عشرة إنذارات كاذبة يُعطَّل في أوّل يوم — وهو عطل الحارس الأكثر شيوعاً في هذا
   المستودع، مسجَّل مراراً.

   بصمة فساد union **بنيويّة ومميِّزة**: العنوانان **متلاصقان** (سطران متتاليان بلا
   متن بينهما)، لأنّ union يضمّ نسختَي **السطر الواحد**. والسلسلة التاريخيّة الشرعيّة
   يفصلها متن دائماً. المقيس على الشجرة: **١ من ١١** متلاصق — وهي إصابة حقيقيّة
   موجودة أصلاً (`BRANCH-GRAVEYARD-POLICY`)، أي أنّ الحارس وجد فساداً قائماً قبل أن
   يُوصَل.

③ **ونسخُ النصّ لا الهويّة** (`UNION-MERGE-DUPLICATES-EDITED-LOG-AND-LEDGER-ENTRIES-SILENTLY-01`):
   رؤوسُ `log.md`/`ledger.md` تواريخ لا معرّفات، فكان تصحيحُ آخرِ مدخلٍ بجوار إلحاقٍ
   يترك النسختين معاً والحارسُ أخضر. شبكةٌ ثالثة تقرأ **النصّ داخل المدخل** — القواعد
   وحدودها عند `NEAR_DUPLICATE_TARGETS`، والتكراراتُ القائمة في أساسٍ مُجمَّد يتقلّص.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard` و`brain_commit_claim_guard`.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]

# الملفّات الأربعة المقيسة بوصفها إلحاقيّة ومتعدّدة الكتّاب: 89 + 77 + 75 + 32 =
# **٢٧٣ من ٢٨١** لمسة على `sahool-brain/` منذ 2026-07-01. وهي نفسها المسارات التي
# يشملها `merge=union` في `.gitattributes` — الشبكة والحارس على **نفس النطاق** عمداً،
# فبقعةٌ يضمّها union ولا يفحصها الحارس هي بالضبط الثغرة التي وُجِد ليسدّها.
#
# ليست glob: `sahool-brain/**/*.md` يشمل رنبوكات ووثائق ليست إلحاقيّة، فيصير الحارس
# يحكم على ملفّات لم تُقَس. المقيس اليوم: registry=99 عنواناً بمعرّف · ledger=11 ·
# log=2 · hot=0 — والأربعة نظيفة من التلاصق بعد إصلاح `BRANCH-GRAVEYARD-POLICY`.
DEFAULT_TARGETS = (
    "sahool-brain/gaps/registry.md",
    "sahool-brain/hot.md",
    "sahool-brain/log.md",
    "sahool-brain/decisions/ledger.md",
)

# معرّف فجوة: مقطعان كبيران فأكثر بشرطات، في **بداية عنوان `## `**.
# `^##` مع `re.M` مرساة أساسيّة: ذكرُ معرّف داخل فقرة ليس إعلان حالة، ومطابقته
# تُنتج نفس صنف الإيجابيّ الكاذب الذي أسقط `CONFLICT_RE` غير المُرسى في #768.
HEADING_RE = re.compile(
    r"^##\s+(?P<gap_id>[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)+)\b",
)

# **وصفُّ جدولٍ إعلانُ حالةٍ كالعنوان تماماً.** `gaps/registry.md` — وهو الموضع الذي
# تعيش فيه هويّاتُ الفجوات أصلاً — جدولٌ لا عناوين، فكانت تغطيةُ هذا الحارس له
# **صفراً**: مرّ أخضرَ على صفّين متلاصقين لنفس المعرّف. أمسك التكرارَ مراجعٌ آليّ
# على #882 لا الحارسُ الموضوع لأجله بعينه.
#
# ومرساةُ `|` تُبقي الصرامة نفسها: ذكرُ معرّفٍ داخل خليّةٍ أخرى أو نثرٍ ليس إعلانَ
# حالة، ولا يُطابَق — فلا يعود الإيجابيّ الكاذب الذي أُرسِيت `^##` لمنعه.
ROW_RE = re.compile(
    r"^\|\s*(?P<gap_id>[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)+)\s*\|",
)

# **وشبكةُ التلاصق وحدها لا تكفي للصفوف** — `BRAIN-DUP-ROW-ESCAPES-THE-ADJACENCY-NET-01`:
# دمجُ union عبر PRs متتابعة أعاد صفَّ `GATE-READS-…-01` صفّاً مستقلّاً **غيرَ متلاصق**
# (بينهما صفُّ #914)، فمرّ الحارسُ أخضرَ عليه. دلالةُ الجدول تفرُّدٌ عالميّ: كلُّ صفٍّ
# إعلانُ الحالةِ الوحيدِ لفجوته — بخلاف العناوين، حيث السلاسلُ التاريخيّةُ المقصودة
# **مقيسةٌ قائمة** (`SPECTRAL-…` في 1478/1489 و`SILENT-EXCEPTION-…` في 1582/1590/1601)
# فالتفرُّدُ العالميّ عليها يُعيد العشرة إنذاراتٍ كاذبة التي رفضها التصميم الأوّل.
#
# وهويّةُ الفحص العالميّ **الخليّةُ الأولى كاملةً بالنقاط**: نمطُ ROW_RE يقف عند
# النقطة، فيقرأ `WAIVER-WX10.6-001` و`WAIVER-WX10.7-001` — إعفاءان متمايزان
# مشروعان — هويّةً واحدة `WAIVER-WX10` ويرفع إنذاراً كاذباً (مقيس على الشجرة).
ROW_FULL_ID_RE = re.compile(
    r"^\|\s*(?P<gap_id>[A-Z][A-Z0-9_.]*(?:-[A-Z0-9_.]+)+)\s*\|",
)

# الفحص العالميّ محصورٌ في الملفّ الذي صفوفُه إعلاناتُ حالةٍ وحيدة.
GLOBAL_ROW_UNIQUENESS_TARGETS = frozenset({"sahool-brain/gaps/registry.md"})

_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# ── UNION-MERGE-DUPLICATES-EDITED-LOG-AND-LEDGER-ENTRIES-SILENTLY-01 ──
#
# رؤوسُ `log.md`/`ledger.md` تاريخٌ لا معرّف (`## 2026-10-14 — …`)، فلا يراها
# `HEADING_RE` أصلاً. والقياسُ في مستودعٍ مؤقّت صحّح الفرضيّة الأولى («عنوانٌ يتكرّر»):
# حين يُصحِّح جانبٌ آخرَ مدخلٍ ويُلحِق الآخرُ بعده، يضمّ union **الأسطرَ المحرَّرة وحدها**
# (المحرَّرة ثمّ الأصليّة، متتاليتين) لا المدخلَ كلَّه — والعنوانُ لا يتكرّر إلّا إن كان
# داخل الكتلة المحرَّرة. فالبصمةُ **سطرٌ ونسخةٌ شبهُ مطابقةٍ له داخل المدخل نفسه**:
#
#   ① متطابقان حرفيّاً بعد تطبيع المسافات            — أيّاً كان بُعدهما داخل المدخل؛
#   ② أحدُهما بادئةُ الآخر (تصحيحٌ أضاف ذيلاً)         — داخل المدخل كذلك؛
#   ③ تشابهٌ ≥ 0.9 (SequenceMatcher) — **داخل الكتلة المتّصلة وحدها** (لا سطرَ فارغاً
#      بينهما): union يضع النسختين في الكتلة نفسها، والقيدُ يُسقط الإيجابيّ الكاذب
#      الوحيد المقيس (قالبا «سجلٌّ متأخّرُ الدمج (#1128)/(#1130)» بتشابه 0.932 في
#      فقرتين منفصلتين، log.md:9131/9138 على 5472740e)؛
#   ④ وقاعدةُ المدخل: عنوانان متطابقان حرفيّاً ومتناهما متشابهان ≥ 0.9 ⇒ مدخلٌ نُسِخ.
#      الرأسُ المكرَّر بمتنٍ مختلف (تاريخٌ واحد لموضوعين) يمرّ.
#
# «سطرٌ جوهريّ» ≥ 30 حرفاً بعد التطبيع وليس فاصلَ جدول: القصيرُ (`- لا شيء`) يتكرّر
# شرعاً. والمقيسُ على سجلّ التعديلات الفعليّة في تاريخ الملفّين (41 سطراً عُدِّل في
# مكانه): ① + ② + ③ تلتقط 28 منها لو ضُمَّت؛ والـ13 الباقية تعديلاتٌ أعمق (< 0.9) —
# حدٌّ مُعلَن لا مُخفى. والعلاجُ البنيويّ (شظايا لا union) يبقى
# `BRAIN-FRAGMENTED-SOURCE-OF-TRUTH-01`؛ هذا يكشف العَرَض لا يمنع السبب.
NEAR_DUPLICATE_TARGETS = frozenset({"sahool-brain/log.md", "sahool-brain/decisions/ledger.md"})
NEAR_DUPLICATE_MIN_CHARS = 30
NEAR_DUPLICATE_RATIO = 0.9
_ENTRY_HEADING_RE = re.compile(r"^#{1,6}\s")
_TABLE_RULE_RE = re.compile(r"^[|:\-\s]+$")

# **الأساسُ المُجمَّد — يتقلّص ولا ينمو.** تكراراتُ union القائمة على main عند
# 5472740e: لا تُحذف (الملفّان إلحاقيّان و`brain_append_only_guard` يمنع التقلّص)، بل
# تُسمّى هنا بالضبط: (المسار، بصمةُ السطر الأوّل، بصمةُ الثاني) ⇒ عددُ الأزواج المسموح.
# البصمة = أوّل 16 من sha256 للسطر بعد تطبيع المسافات. نسخةٌ ثالثةٌ من السطر نفسه
# تزيد العدد فتحجب؛ ومدخلٌ لم يعد يطابق شيئاً بائتٌ يُحذف (`stale_baseline_entries`).
# لا يُضاف إليه سطر: تكرارٌ جديد يُعالَج في النصّ (يُدمَج المدخلان بنصّ صحيح) لا هنا.
NEAR_DUPLICATE_BASELINE: dict[tuple[str, str, str], int] = {
    # log.md:7875 ≡ 7879 — «مهلةٌ لكلّ زرعة في مكنسة الطفرات…» (2026-09-17)
    ("sahool-brain/log.md", "91ea5ba2036359d2", "91ea5ba2036359d2"): 1,
    # log.md:7876 ≡ 7880 — «CI على #1015 (`bc443deb`)…» (2026-09-17)
    ("sahool-brain/log.md", "65b06f06503028e7", "65b06f06503028e7"): 1,
    # ledger.md:2102 ≡ 2104 — «حدُّ صدق: لم أقِس بقيّةَ #952…» (2026-08-27 (د))
    ("sahool-brain/decisions/ledger.md", "cc5ea72a22c9cb20", "cc5ea72a22c9cb20"): 1,
    # ledger.md:2103 ≡ 2105 — «المصدر: قياسُ هذه الجلسة على `7c118b54`…»
    ("sahool-brain/decisions/ledger.md", "46f0dd62ce1e96d9", "46f0dd62ce1e96d9"): 1,
}


def _strip_fenced_blocks(lines: list[str]) -> list[str | None]:
    """يُعيد الأسطر مع `None` مكان ما هو داخل كتلة كود.

    عنوانٌ داخل ``` مثالٌ في وثيقة لا سجلّ — وهذا الملفّ **يشرح** الحارس بأمثلة،
    فبلا هذا الاستبعاد يُطلِق الحارس على توثيقه لنفسه.
    """
    out: list[str | None] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(None)
            continue
        out.append(None if in_fence else line)
    return out


def adjacent_duplicate_identities(text: str) -> list[tuple[str, int, int]]:
    """عناوين متلاصقة تحمل نفس معرّف الفجوة: (المعرّف، سطر الأوّل، سطر الثاني).

    «متلاصقان» = سطران متتاليان **كلاهما عنوان** لنفس المعرّف. هذا هو ما ينتجه
    union حين يضمّ نسختَي سطر واحد؛ والسلسلة التاريخيّة يفصلها متن فتمرّ.
    """
    # `splitlines()` يتولّى CRLF وLF معاً، فلا حاجة لتطبيع منفصل.
    lines = _strip_fenced_blocks(text.splitlines())
    ids: list[str | None] = []
    for line in lines:
        if line is None:
            ids.append(None)
            continue
        m = HEADING_RE.match(line) or ROW_RE.match(line)
        ids.append(m.group("gap_id") if m else None)

    found: list[tuple[str, int, int]] = []
    for i in range(len(ids) - 1):
        if ids[i] is not None and ids[i] == ids[i + 1]:
            found.append((ids[i], i + 1, i + 2))  # أسطر 1-based
    return found


def global_duplicate_row_identities(text: str) -> list[tuple[str, list[int]]]:
    """صفوف جدولٍ تُعلِن نفس هويّة الفجوة أكثر من مرّة — أينما وقعت، لا تلاصقاً.

    صفوفٌ فقط (العناوين تحمل سلاسل تاريخيّة مشروعة)، وبهويّة الخليّة الكاملة
    بالنقاط (وإلّا قُرِئ إعفاءان متمايزان `WAIVER-WX10.6/.7` هويّةً واحدة).
    """
    lines = _strip_fenced_blocks(text.splitlines())
    seen: dict[str, list[int]] = {}
    for i, line in enumerate(lines):
        if line is None:
            continue
        m = ROW_FULL_ID_RE.match(line)
        if m:
            seen.setdefault(m.group("gap_id"), []).append(i + 1)
    return [(gap_id, at) for gap_id, at in seen.items() if len(at) > 1]


def _normalize(line: str) -> str:
    return " ".join(line.split())


def line_fingerprint(line: str) -> str:
    """بصمةُ سطرٍ للأساس المُجمَّد: أوّل 16 من sha256 بعد تطبيع المسافات."""
    return hashlib.sha256(_normalize(line).encode("utf-8")).hexdigest()[:16]


def _near_copy(a: str, b: str, *, allow_ratio: bool) -> str | None:
    """نوعُ التطابق بين سطرين مُطبَّعين، أو None."""
    if a == b:
        return "identical"
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if long_.startswith(short):
        return "prefix-edit"
    if not allow_ratio:
        return None
    # مُرشِّحٌ رخيص قبل SequenceMatcher: تشابهُ 0.9 في الحروف يُبقي أغلبَ الكلمات.
    ta, tb = set(a.split()), set(b.split())
    if len(ta & tb) * 2 < max(len(ta), len(tb)):
        return None
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < NEAR_DUPLICATE_RATIO or sm.quick_ratio() < NEAR_DUPLICATE_RATIO:
        return None
    ratio = sm.ratio()
    return f"ratio={ratio:.3f}" if ratio >= NEAR_DUPLICATE_RATIO else None


def near_duplicate_lines(text: str) -> list[tuple[int, int, str]]:
    """أسطرٌ نُسِخت داخل مدخلٍ واحد — بصمةُ union على مدخلٍ مُصحَّح: (سطر، سطر، النوع).

    القواعد ①–④ في تعليق `NEAR_DUPLICATE_TARGETS`. الأسطر 1-based بترتيب الملفّ.
    """
    lines = _strip_fenced_blocks(text.splitlines())
    entry_of: list[int] = []
    block_of: list[int] = []
    entry = block = 0
    for line in lines:
        if line is not None and _ENTRY_HEADING_RE.match(line):
            entry += 1
        if line is None or not line.strip():
            block += 1
        entry_of.append(entry)
        block_of.append(block)

    def substantive(i: int) -> str | None:
        line = lines[i]
        if line is None or _TABLE_RULE_RE.match(line):
            return None
        norm = _normalize(line)
        return norm if len(norm) >= NEAR_DUPLICATE_MIN_CHARS else None

    # النطاقان: المدخل (① ②، ③ إن كانا في كتلةٍ واحدة) والكتلة المتّصلة (① ② ③ ولو
    # عبرت عنواناً: مدخلٌ قصيرٌ حُرِّر عنوانُه ومتنُه يُضَمّ «عنوانٌ′ متنٌ′ عنوانٌ متنٌ»).
    groups: dict[tuple[str, int], list[tuple[int, str]]] = {}
    for i in range(len(lines)):
        norm = substantive(i)
        if norm is not None:
            groups.setdefault(("entry", entry_of[i]), []).append((i, norm))
            groups.setdefault(("block", block_of[i]), []).append((i, norm))

    seen: set[tuple[int, int]] = set()
    found: list[tuple[int, int, str]] = []
    for members in groups.values():
        for x, (i, a) in enumerate(members):
            for j, b in members[x + 1 :]:
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                kind = _near_copy(a, b, allow_ratio=block_of[i] == block_of[j])
                if kind:
                    found.append((i + 1, j + 1, kind))

    # ④ مدخلٌ نُسِخ كاملاً: عنوانٌ حرفيٌّ مكرَّر ومتناهما متشابهان.
    headings: dict[str, list[int]] = {}
    bodies: dict[int, list[str]] = {}
    for i, line in enumerate(lines):
        if line is not None and _ENTRY_HEADING_RE.match(line):
            headings.setdefault(_normalize(line), []).append(i)
        elif line is not None and line.strip():
            bodies.setdefault(entry_of[i], []).append(_normalize(line))
    for at in headings.values():
        for x, i in enumerate(at):
            for j in at[x + 1 :]:
                body_i = " ".join(bodies.get(entry_of[i], []))
                body_j = " ".join(bodies.get(entry_of[j], []))
                if body_i == body_j or (
                    SequenceMatcher(None, body_i, body_j, autojunk=False).ratio()
                    >= NEAR_DUPLICATE_RATIO
                ):
                    found.append((i + 1, j + 1, "duplicated-entry"))
    return sorted(found)


def _grouped_near_duplicates(
    rel: str, text: str
) -> dict[tuple[str, str, str], list[tuple[int, int, str]]]:
    lines = text.splitlines()
    grouped: dict[tuple[str, str, str], list[tuple[int, int, str]]] = {}
    for a, b, kind in near_duplicate_lines(text):
        key = (rel, line_fingerprint(lines[a - 1]), line_fingerprint(lines[b - 1]))
        grouped.setdefault(key, []).append((a, b, kind))
    return grouped


def stale_baseline_entries(rel: str, text: str) -> list[tuple[str, str, str]]:
    """مداخلُ الأساس لهذا الملفّ التي لم تعد تطابق شيئاً — تُحذَف (الأساس يتقلّص).

    يُفرَض باختبارٍ على الشجرة الحيّة لا داخل `check()`: الحارسُ يُشغَّل أيضاً على
    أشجارٍ مُصغَّرة (عقد preflight)، وهناك غيابُ السطور المُعفاة ليس بوَاراً.
    """
    grouped = _grouped_near_duplicates(rel, text)
    return [key for key in NEAR_DUPLICATE_BASELINE if key[0] == rel and key not in grouped]


def near_duplicate_findings(rel: str, text: str) -> list[str]:
    """التكراراتُ الجديدة — ما زاد على الأساس المُجمَّد."""
    grouped = _grouped_near_duplicates(rel, text)
    problems: list[str] = []
    for key, hits in grouped.items():
        if len(hits) <= NEAR_DUPLICATE_BASELINE.get(key, 0):
            continue
        for a, b, kind in hits:
            problems.append(
                f"near-duplicate entry text ({kind}) — union on an edited entry?\n"
                f"  {rel}:{a}\n  {rel}:{b}"
            )
    return problems


def check(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if not path.exists():
            problems.append(f"هدف مفقود: {path.relative_to(ROOT)}")
            continue
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for gap_id, first, second in adjacent_duplicate_identities(text):
            problems.append(f"duplicate gap identity: {gap_id}\n  {rel}:{first}\n  {rel}:{second}")
        if rel in GLOBAL_ROW_UNIQUENESS_TARGETS:
            for gap_id, at in global_duplicate_row_identities(text):
                where = "\n".join(f"  {rel}:{n}" for n in at)
                problems.append(f"duplicate gap ROW (global): {gap_id}\n{where}")
        if rel in NEAR_DUPLICATE_TARGETS:
            problems.extend(near_duplicate_findings(rel, text))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "targets",
        nargs="*",
        default=list(DEFAULT_TARGETS),
        help="مسارات نسبيّة للجذر (الافتراضيّ: سجلّ الفجوات)",
    )
    args = parser.parse_args()

    problems = check([ROOT / t for t in args.targets])
    if problems:
        print(
            "تكرارٌ صامت تتركه union — عناوين متلاصقة بنفس الهويّة، أو صفّ سجلٍّ مكرَّر،\n"
            "أو نصّ مدخلٍ نُسِخ في log/ledger (النسخة المحرَّرة بجوار الأصليّة):"
        )
        for line in problems:
            print(f"  ✗ {line}")
        print(
            "\nالعلاج: ادمج العنوانين في مدخل واحد يحفظ نصّيهما، أو افصلهما بمتن إن\n"
            "كانا حالتين تاريخيّتين مختلفتين. لا تحذف أحدهما بلا قراءة — الجانبان\n"
            "جاءا من جلستين، وحذف أحدهما يمحو عمل جلسة.\n"
            "ولنصّ مدخلٍ مكرَّر في log/ledger: أعِد حلَّ الدمج نفسه بإبقاء النسخة المصحَّحة\n"
            "وحدها (لا بالتزامٍ لاحق يحذف — `brain_append_only_guard` يقيس كلَّ التزام)؛ وإن\n"
            "قُصِدت النسختان فاجعل التصحيحَ مدخلاً جديداً بعنوانه. ولا يُضاف شيءٌ إلى\n"
            "NEAR_DUPLICATE_BASELINE — أساسٌ مُجمَّد يتقلّص فقط."
        )
        return 1

    print(
        "brain_duplicate_gap_identity_guard: PASS "
        "(لا عناوين متلاصقة متطابقة الهويّة، ولا صفّ سجلٍّ يُعلَن مرّتين، "
        "ولا نصّ مدخلٍ مكرَّر في log/ledger خارج الأساس المُجمَّد)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

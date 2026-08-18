#!/usr/bin/env python3
"""انتظارٌ بلا سقف — `CI-UNBOUNDED-PROVISIONING-WAIT-01`، الشطر الذي يمنع العودة.

**الحادثة، مقيسةً لا مفترَضة.** في تشغيل 32073296568 علقت وظيفة `Integration Tests`
**مئةً واثنتي عشرة دقيقة** ثمّ بقيت معلَّقة. والسجلّ يحصر الموضع: سحبُ الصورتين
اكتمل (`Status: Downloaded newer image` لكلتيهما)، ومعرّفا الحاويتين طُبِعا — أي أنّ
`docker run` عاد؛ ثمّ صمت. والخطوة التالية `apt-get`، وبعدها حلقةُ الجاهزيّة التي
لم يظهر منها سطرٌ واحد. والحلقة مسقوفة (٣٠×٢ث و`pg_isready` مسقوف بثلاث ثوانٍ)
فأقصاها دقيقتان ونصف؛ و`pg_isready` يطبع حالته فبلوغُها كان سيترك أثراً. فلم يبقَ
إلّا تعليقٌ داخل APT. **والسبب** — مرآة أو DNS أو قفل — غير مُثبَت، والعلاج لا
يحتاجه: حدٌّ جداريّ يُحوّل الصمت إلى فشلٍ مُسمّى.

**والمواضع أُصلحت في `#868`.** فما يفعله هذا الملفّ ليس الإصلاح بل **منع عودته**:
الإصلاح يُغلق ثلاث حالات، ولا شيء كان يمنع رابعةً من الدخول غداً. وهذا هو الفرق
المُسجَّل في هذا المستودع بين «أصلحتُ ما وقع» و«منعتُ أن يقع».

**القاعدتان — كلٌّ تُقاس وحدها:**

  ① كلّ وظيفة تُقيم حاوية قاعدة بيانات تحمل `timeout-minutes`. الافتراضيّ عند
     GitHub **360 دقيقة**، فتعليقٌ واحد يحرق runner ستّ ساعات صامتاً.
  ② لا `apt-get` بلا `timeout` في أيّ workflow. (وليس «APT بلا مهلة» — له
     `Acquire::http::Timeout`؛ الغائب حدٌّ **جداريّ** على الخطوة.)

**وقاعدةٌ ثالثة حُذِفت لأنّ القياس كذّبها، والتصريح بها جزءٌ من الصدق:** كنتُ
أفرض «لا `pg_isready` من المضيف — اسألها داخل الحاوية». وقِيس في تشغيل
32125050692 أنّ ذلك **يكسر** التجهيز: `pg_isready` عبر مقبس يونكس داخل الحاوية
يقول «accepting connections» أثناء طور التهيئة — نقطةُ دخول صورة postgres تُشغّل
خادماً مؤقّتاً ثمّ تُعيد تشغيله — فكسرت الحلقة وسقط الفحص النهائيّ بـ«no response».
فالاستجواب من المضيف عبر TCP على المنفذ المُسنَد ليس نقصاً يُصلَح، بل هو **المقياس
الصحيح**: لا يُجيب إلّا حين يقبل الخادم النهائيّ اتّصالاً خارجيّاً.

**وما لا يفعله، والحدّ مُعلَن:** لا يقيس **كفاية** السقف (٣٠ دقيقة أم ٦٠) — ذلك
حكمٌ لكلّ وظيفة؛ يقيس **وجوده**. ولا يفرض شكل إعادة المحاولة حول `apt-get`.

    python scripts/ci/ci_unbounded_wait_guard.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"

# وظائف تُقيم حاوية قاعدة بيانات ⇒ يجب أن تحمل سقفاً.
_DB_JOB_MARKERS = ("docker run -d --name",)

# `timeout` قد يسبق `sudo` أو يتلوه — كلاهما حدٌّ جداريّ صحيح.
_BOUNDED_APT = re.compile(r"\btimeout\b[^|;&]*\bapt-get\b")

# نصٌّ داخل اقتباس **ذِكرٌ لا استدعاء**: رسالةُ `echo "apt-get تعثّر…"` تصف العطل
# ولا ترتكبه. وإدانتُها إيجابيّةٌ كاذبة تُسقِط الحارس بلا أن تُعطّله — قارئ الأحمر
# يتعلّم تجاهله. (وقعت فعلاً على `ci.yml:839-840` أوّل تشغيل.)
_QUOTED = re.compile(r"\'[^\']*\'|\"[^\"]*\"")


def _commands_only(line: str) -> str:
    """يُسقِط ما بين الاقتباسات فيبقى ما يُنفَّذ وحده."""
    return _QUOTED.sub(" ", line)


def findings() -> list[str]:
    import yaml

    out: list[str] = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        rel = wf.relative_to(ROOT).as_posix()

        # ② apt-get بلا سقف جداريّ.
        for i, line in enumerate(text.splitlines(), 1):
            stripped = _commands_only(line.strip())
            if line.strip().startswith("#") or "apt-get" not in stripped:
                continue
            if not _BOUNDED_APT.search(stripped):
                out.append(f"{rel}:{i}: apt-get بلا `timeout` — اعتمادٌ شبكيّ غير مسقوف")

        # ① سقف الوظيفة.
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:  # وثيقةٌ لا تُقرأ فشلٌ مغلق لا تخطٍّ
            out.append(f"{rel}: تعذّرت قراءة الـYAML: {exc}")
            continue
        for job_id, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            body = "\n".join(
                str(step.get("run", ""))
                for step in (job.get("steps") or [])
                if isinstance(step, dict)
            )
            if any(m in body for m in _DB_JOB_MARKERS) and not job.get("timeout-minutes"):
                out.append(
                    f"{rel}: وظيفة {job_id} تُقيم حاوية قاعدة بلا `timeout-minutes` "
                    "⇒ تعليقٌ واحد يحرق runner ستّ ساعات"
                )
    return out


def main() -> int:
    f = findings()
    if f:
        print("ci_unbounded_wait_fail")
        for x in f:
            print(" -", x)
        return 1
    print("ci_unbounded_wait_ok: كلّ تجهيزٍ لقاعدة مسقوف — وظيفةً وأمرَ شبكة")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

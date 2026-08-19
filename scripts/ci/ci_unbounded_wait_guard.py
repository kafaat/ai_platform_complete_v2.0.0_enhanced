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

**القواعد — كلٌّ تُقاس وحدها:**

  ① كلّ وظيفة تُجهّز اعتماداً شبكيّاً — حاوية قاعدة بيانات **أو** أداةً تجلب حِزَماً —
     تحمل `timeout-minutes`. الافتراضيّ عند GitHub **360 دقيقة**، فتعليقٌ واحد يحرق
     runner ستّ ساعات صامتاً.
  ② لا `apt-get` بلا `timeout` في أيّ workflow. (وليس «APT بلا مهلة» — له
     `Acquire::http::Timeout`؛ الغائب حدٌّ **جداريّ** على الخطوة.)
  ③ ولا أداةً **تستدعي APT من جوفها** بلا `timeout`. وهذه أُضيفت بعد أن أفلت منها
     العطلُ نفسه: `npx playwright install --with-deps` يُشغّل `apt-get` داخله، فلا
     يراه ماسحٌ يبحث عن `apt-get` **نصّاً** في الـworkflow، ولم تكن وظيفته تُقيم
     حاوية قاعدة فلم تطلب ① سقفاً لها. فبقيت بلا حدَّين معاً. **مقيس على هذا
     المستودع:** التشغيل 32160054946 علق فيها **٨٠+ دقيقة** وحجب PR شجرتُه خضراء،
     بينما نجحت الخطوة نفسها على **الرأس نفسه بالبايت** في التشغيل الشقيق
     32160058172 في **دقيقتين وخمس وخمسين ثانية**. والدرس أعمّ من الأداة: حدٌّ
     يُفرَض على **اسم الأمر** يفوته كلُّ من يستدعيه من جوفه.

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

# تجهيزٌ شبكيّ ⇒ الوظيفة يجب أن تحمل سقفاً.
#
# والعلامة الثالثة (`scripts/ci/resilient_`) أُضيفت بعد أن **عمي الحارس بإصلاحٍ صحيح**
# للمرّة الثالثة في هذه السلسلة: نقلُ `playwright install --with-deps` إلى سكربتٍ
# صامد أخرج السلسلة من متن الوظيفة، فصارت ① لا ترى تجهيزاً شبكيّاً فيها ولا تطلب
# سقفاً — والسقف كان قائماً فمرّ الحارس **أخضرَ لسببٍ خاطئ**. مقيس بالزرع: نزعُ
# `timeout-minutes` من `frontend-e2e` لم يُدَن قبل هذه العلامة.
#
# وهي بالبادئة لا بالأسماء: سكربتات `resilient_*` موجودةٌ **لأنّها تجلب من الشبكة**
# (`apt` · `docker pull` · متصفّحات Playwright)، فالبادئة تصف الصنف لا تعدّ أفراده،
# ويرثها من يُضاف غداً بلا تعديل هنا.
_DB_JOB_MARKERS = ("docker run -d --name", "--with-deps", "scripts/ci/resilient_")

# `timeout` قد يسبق `sudo` أو يتلوه — كلاهما حدٌّ جداريّ صحيح.
_BOUNDED_APT = re.compile(r"\btimeout\b[^|;&]*\bapt-get\b")

# أدواتٌ تستدعي مدير حِزَم من جوفها. القائمة **مقيسة لا مُتخيَّلة**: يُضاف إليها ما
# وقع هنا فعلاً. وتوسيعها بالتخمين يُنتِج إدانات لا يفهمها قارئها.
_APT_INVOKING_TOOLS = ("playwright install --with-deps",)


def _bounded_tool(line: str, tool: str) -> bool:
    """أيقع `timeout` على **هذا الأمر بعينه**؟

    المعيار هو معيار القاعدة ② حرفيّاً: `timeout` ثمّ اسمُ الأداة بلا فاصل أمرٍ
    بينهما (`| ; &`). وأوّل صياغةٍ استعملت `match` — أي «يبدأ السطر بـtimeout» —
    فأدانت `if timeout … npx playwright install …; then` وهو **مسقوفٌ فعلاً**.
    إيجابيّةٌ كاذبة تُسقِط الحارس بلا أن تُعطّله، فيتعلّم قارئ الأحمر تجاهله؛
    وقعت على أوّل تشغيلٍ بعد كتابة `resilient_playwright_install.sh`.
    """
    return re.search(r"\btimeout\b[^|;&]*" + re.escape(tool), line) is not None


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

    # النطاق **الـworkflows وسكربتات `scripts/ci/*.sh` معاً**. والسبب مقيس على هذه
    # الشريحة نفسها: نقلُ كتلة APT من ثلاث `run:` إلى سكربتٍ واحد أخرجها من مدى
    # حارسٍ يمسح الـworkflows وحدها — فكان **إصلاحٌ يفتح ثغرة**، وهو نفس درس ③:
    # حدٌّ مربوطٌ بموضعٍ يفوته من ينتقل عنه. يُمسح الموضعان فلا يُنجِي النقل.
    scanned = sorted(WORKFLOWS.glob("*.yml")) + sorted((ROOT / "scripts/ci").glob("*.sh"))
    for wf in scanned:
        text = wf.read_text(encoding="utf-8")
        rel = wf.relative_to(ROOT).as_posix()

        # ② apt-get بلا سقف جداريّ.
        for i, line in enumerate(text.splitlines(), 1):
            stripped = _commands_only(line.strip())
            if line.strip().startswith("#") or "apt-get" not in stripped:
                continue
            if not _BOUNDED_APT.search(stripped):
                out.append(f"{rel}:{i}: apt-get بلا `timeout` — اعتمادٌ شبكيّ غير مسقوف")

        # ③ أداةٌ تستدعي APT من جوفها، بلا سقف جداريّ.
        for i, line in enumerate(text.splitlines(), 1):
            stripped = _commands_only(line.strip())
            if line.strip().startswith("#"):
                continue
            for tool in _APT_INVOKING_TOOLS:
                if tool in stripped and not _bounded_tool(stripped, tool):
                    out.append(
                        f"{rel}:{i}: `{tool}` بلا `timeout` — يستدعي apt-get من جوفه "
                        "فلا تبلغه القاعدة ②"
                    )

        # ① سقف الوظيفة — على الـworkflows وحدها: السكربت لا يملك `timeout-minutes`،
        # وسقفُه يفرضه مُستدعيه. وتمريرُ نصّ shell إلى `yaml.safe_load` يُعيد سلسلة
        # فيسقط الحارس بـAttributeError — انهيارٌ يُقرأ حجباً وهو عطلٌ فيه.
        if wf.suffix != ".yml":
            continue
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
            hit = next((m for m in _DB_JOB_MARKERS if m in body), None)
            if hit and not job.get("timeout-minutes"):
                # الرسالة تسمّي **ما وُجِد**، لا صنفاً واحداً افتراضاً: حارسٌ وسّع مداه
                # وأبقى نصّه يُدين «حاوية قاعدة» في وظيفةٍ لا حاوية فيها يُقرأ خطأً
                # فيُصلَح الخطأ الخطأ. (وقعت هنا فعلاً أوّل تشغيل بعد التوسعة.)
                out.append(
                    f"{rel}: وظيفة {job_id} تُجهّز اعتماداً شبكيّاً (`{hit}`) بلا "
                    "`timeout-minutes` ⇒ تعليقٌ واحد يحرق runner ستّ ساعات"
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

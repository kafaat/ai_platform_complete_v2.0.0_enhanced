#!/usr/bin/env python3
"""عقد الزمن الحتميّ للمصنوعات المولَّدة — `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`.

**العلّة المقيسة، لا المفترضة.** `release/SAHOOL_RELEASE_MANIFEST_20260626.json` هو
أكثر ملفّ حركةً في الشجرة (**١٢٨** التزاماً منذ 2026-07-01)، وكان يكتب
`datetime.now(UTC).isoformat()` — ختماً بدقّة الميكروثانية من **ساعة الحائط**.

وتفصيل الحركة، بعد إعادة قياس صحّحت رقماً قلتُه أوّلاً («٧٤ ختماً فقط»، وكان تقريباً
خشناً): **٣** التزامات غيّرت `generated_at` **وحده** · **٧١** غيّرته مع
`file_count`/`total_size_bytes` أي مع حمولة تغيّرت فعلاً · **٥٢** محتوى آخر.

فالمكسب ليس «إلغاء ٧٤ التزاماً» بل خاصّيّة أدقّ وأقوى: **إعادة التوليد على شجرة لم
تتغيّر حمولتها تُنتج الآن صفر فرق** بدل فرق سطريّ مضمون — وهي ما يحوّل «أعِد التوليد
قبل الالتزام» من مصدر تعارض إلى عمليّة محايدة. وقبلها كان فرعان يُعيدان التوليد في
لحظتين مختلفتين يكتبان قيمتين مختلفتين في **نفس السطر**، فيتعارضان حتّى لو كانت
الحمولة متطابقة تماماً.

الحلّ معياريّ لا مُبتكَر: `SOURCE_DATE_EPOCH` من مبادرة Reproducible Builds — زمنٌ
مشتقّ من **المصدر** لا من ساعة الحائط.

**والقاعدة الحاسمة أنّ الارتداد إلى الساعة ممنوع.** كتابة::

    epoch = int(os.getenv("SOURCE_DATE_EPOCH") or time.time())   # ← خطأ

تُعيد اللاحتميّة **صامتةً**: تعمل في CI (حيث المتغيّر مضبوط) وتفشل عند المطوّر بلا
رسالة تُفسّر لماذا انحرفت مصنوعته. فالعقد ثلاثيّ صريح:

  ① `SOURCE_DATE_EPOCH` مضبوط وصالح ⇒ استعمله.
  ② وإلّا وgit متاح بتاريخ ⇒ ختم آخر التزام (`git log -1 --pretty=%ct`).
  ③ وإلّا ⇒ **افشل صراحةً**.

و③ ليست تزمّتاً. المولّد قد يعمل داخل أرشيف بلا `.git`، أو في حاوية بتاريخ مبتور
(`--depth=1` يُبقي التزاماً واحداً فيبقى ② صالحاً، لكنّ نسخة بلا `.git` أصلاً لا)،
أو في اختبار على `tmp_path`. في كلّ تلك الحالات الصمتُ يُنتج مصنوعة تدّعي الحتميّة
وليست حتميّة — وهو أسوأ من رفضٍ يُقرأ.

يعمل بلا تبعيّات خارجيّة (stdlib فقط) لأنّ مستهلكيه سكربتات بناء تعمل في بيئات دنيا.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime

__all__ = ["source_epoch", "generated_at_utc", "DeterministicTimeUnavailable"]


class DeterministicTimeUnavailable(RuntimeError):
    """لا مصدر زمن حتميّ — لا `SOURCE_DATE_EPOCH` ولا تاريخ git."""


_ENV = "SOURCE_DATE_EPOCH"


def source_epoch(*, cwd: str | os.PathLike[str] | None = None) -> int:
    """ثواني epoch حتميّة، أو استثناء صريح.

    `cwd` لأجل الاختبار: يسمح بسؤال مستودع بعينه بدل مجلّد العمليّة.
    """
    raw = os.environ.get(_ENV)
    if raw is not None:
        value = raw.strip()
        try:
            epoch = int(value)
        except ValueError as exc:
            raise ValueError(f"{_ENV} must be an integer, got {raw!r}") from exc
        if epoch < 0:
            raise ValueError(f"{_ENV} must be non-negative, got {epoch}")
        return epoch

    try:
        out = subprocess.run(
            ["git", "log", "-1", "--pretty=%ct"],
            cwd=cwd,
            capture_output=True,
            text=True,
            # الترميز صريح: مخرَج git قد يحمل غير-ASCII في مسارات أخرى، وفكّه
            # بترميز لغة الآلة هو `TEXT-DECODED-WITH-THE-MACHINES-LOCALE-01` عينه.
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        return int(out)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise DeterministicTimeUnavailable(
            f"Deterministic generation requires {_ENV} when git history is unavailable. "
            f"Set it to a fixed epoch (e.g. {_ENV}=$(git log -1 --pretty=%ct)). "
            "Falling back to the wall clock is forbidden: it reintroduces "
            "nondeterminism silently and puts a fresh timestamp into a generated "
            "artifact on every run, which conflicts on every parallel branch."
        ) from exc


def generated_at_utc(*, cwd: str | os.PathLike[str] | None = None) -> str:
    """ختم ISO-8601 بتوقيت UTC مشتقّ من المصدر.

    `Z` لا `+00:00`: الشكلان يعنيان الشيء نفسه، لكنّ تثبيت **شكل** واحد جزءٌ من
    الحتميّة — قارئان يكتبان الشكلين يُنتجان بايتات مختلفة لنفس اللحظة.
    والدقّة **بالثانية** عمداً: الميكروثانية تُقاس من ساعة الحائط فتعود بالمشكلة.
    """
    stamp = datetime.fromtimestamp(source_epoch(cwd=cwd), tz=UTC)
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")

"""سطحُ ملفّات Compose — **مصدر اكتشافٍ واحد** يستهلكه كلّ حارس يمسّها.

`GUARD-SCOPE-SINGLE-FILE` تكرّر في هذا المستودع بأربع معالجات عرضيّة: حارسٌ يُعدَّل
ليرى ملفّاً كان يفوته، ثمّ يفوته ملفٌّ آخر. والعلّة واحدة في كلّها — **كلّ حارس يحمل
قائمته**. فما دام السطح يُعرَّف في أربعة مواضع، فأربعةُ تعريفات تنحرف عن بعضها.

فهنا تعريفٌ واحد. ومَن يستهلكه يرث سطحه، ويرث معه واجبَ الشهود الخمسة
(`GUARD-SCOPE-COMPLETENESS`، دفتر القرارات 2026-08-20):

  ① ``universe_source`` — من أين جاء السطح
  ② ``discovered_paths`` — ماذا رأى
  ③ ``excluded_paths`` — ماذا استبعد **ولماذا**
  ④ شاهدُ **تساوي المجموعات** — لا عدّادات
  ⑤ شاهدُ طفرة — ملفٌّ جديد على السطح يجب أن يراه

**ولمَ التساوي لا العدّ:** عدّادٌ يقول «فُحِص ٩ ملفّات» صادقٌ ومُضلِّل معاً — لا يقول
أيّها، ولا يكشف عاشراً دخل الشجرة. والمجموعة تقول الاثنين.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: النمط المُعلَن للسطح. يُقابَل بالمتعقَّب في git، فلا يبقى ادّعاءً.
UNIVERSE_SOURCE = "git ls-files :(glob)docker-compose*.yml :(glob)frontend/docker-compose*.yml"

#: مستبعَدات مُسمّاة **بسببها**. لا استبعاد بلا سبب مكتوب — الاستبعاد الصامت هو
#: كيف يصير السطح أصغر ممّا يُعتقَد بلا أن يلاحظ أحد.
EXCLUSIONS: dict[str, str] = {}


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", "docker-compose*.yml", "frontend/docker-compose*.yml"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    ).stdout
    return sorted(line for line in out.splitlines() if line.strip())


def compose_files() -> list[Path]:
    """السطح المُكتشَف — متعقَّبٌ في git، لا ما يصادف وجوده على القرص.

    التعقّب هو الفارق: ملفٌّ غير متعقَّب لا يبلغ CI، وملفٌّ متعقَّب يبلغها ولو غاب
    عن نسخةٍ محلّيّة. فالحارس الذي يقيس القرص يقيس آلة كاتبه لا المستودع.
    """
    return [ROOT / rel for rel in _tracked() if rel not in EXCLUSIONS]


def discovery_witness() -> dict[str, object]:
    """الشهود الثلاثة الأولى مُصنَّعةً لا موصوفة — يقرؤها اختبار العقد."""
    tracked = _tracked()
    return {
        "universe_source": UNIVERSE_SOURCE,
        "discovered_paths": [p for p in tracked if p not in EXCLUSIONS],
        "excluded_paths": {k: v for k, v in EXCLUSIONS.items() if k in tracked},
    }

"""فحصُ صحّةِ عاملٍ يفشل **مغلقاً** — ``WEATHER-HEARTBEAT-01``.

الصيغة السابقة كانت تفشل **مفتوحةً** في حالتين، وكلتاهما تجعل الفحص يشهد بصحّةٍ
لم يقسها:

* ``if HEARTBEAT_FILE.exists() and <بائتة>`` — **غيابُ النبضة يمرّ.** الشرط يقصر
  دائرته على غير الموجود، فيبقى المطلوبُ الوحيد وجودَ ملفّ الجاهزيّة، وهو يُكتَب
  مرّةً عند الإقلاع ولا يُحدَّث بعدها. أي أنّ الفحص كان يقيس «العمليّة أقلعت مرّةً»
  ويُعلِنها «العامل يعمل الآن». والبدائيّة القويّة في المنصّة تقول عكسه صراحةً:
  ``evaluate_heartbeat`` تُرجِع ``missing_or_unreadable_heartbeat`` غيرَ صحّيّة.
* ``time.time() - mtime > MAX_AGE`` — **نبضةٌ مؤرَّخة في المستقبل تمرّ.** الفرق يصير
  سالباً فلا يتجاوز أيّ سقف، ويبقى كذلك حتّى يلحق الزمنُ الحقيقيّ بالختم. واختلافُ
  الساعات ليس دليلَ صحّة؛ هو غيابُ دليل.

والسقفُ نفسه لا يجوز أن يكون رقماً مستقلّاً عن **كادنس المنتِج**: العامل يُنعِش
النبضة مرّةً كلّ دورة، فسقفٌ أقصر من الدورة يجعل النبضة بائتةً في وضعها الطبيعيّ.
لذلك يُشتقّ السقف من الكادنس المُعلَن حين يُعلَن (``WORKER_HEARTBEAT_CADENCE_SEC``)
ولا يُترك لرقمٍ ثابت يصادف أن يوافقه.

stdlib فقط بالقصد: يعمل داخل حاوية مُقوّاة بلا تبعيّات ولا وصولِ شبكة.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

READY_FILE = Path(os.getenv("WORKER_READY_FILE", "/tmp/sahool-worker-ready"))
HEARTBEAT_FILE = Path(os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/sahool-worker-heartbeat"))
MAX_AGE = int(os.getenv("WORKER_HEALTH_MAX_AGE_SEC", "180"))
# كادنسُ المنتِج كما يُعلِنه تشغيلُه (0 = غير مُعلَن). يُضبَط في compose من المتغيّر
# نفسه الذي يقرأه العامل، فلا يصير رقمين ينحرفان.
CADENCE = int(os.getenv("WORKER_HEARTBEAT_CADENCE_SEC", "0"))
# سماحُ ساعةٍ صغير: انحرافُ ثوانٍ بين كتابة الملفّ وقراءته ليس عطلاً. وما تجاوزه
# اختلافُ ساعاتٍ حقيقيّ، وهو غيابُ دليلٍ لا دليلُ صحّة.
FUTURE_TOLERANCE_SEC = 5


def effective_max_age(max_age: int = MAX_AGE, cadence: int = CADENCE) -> int:
    """السقفُ الفعليّ: لا يقلّ عن دورتين كاملتين من كادنس المنتِج زائدَ سماح.

    دورتان لا واحدة: دورةٌ واحدة تجعل كلّ تأخّرٍ عابر في دورة يُقرَأ عطلاً، فيصير
    الفحص يقيس **دقّة الجدولة** لا الحياة. والسماحُ يغطّي زمن الدورة نفسها.
    """
    if cadence <= 0:
        return max_age
    return max(max_age, 2 * cadence + 60)


def check(now: float | None = None) -> tuple[bool, str]:
    """منطقٌ صرف — (ok, reason). لا طباعة ولا خروج، فيُكذَّب باختبار."""
    now = time.time() if now is None else now
    if not READY_FILE.exists():
        return False, "not ready: ready file missing"
    if not HEARTBEAT_FILE.exists():
        # يفشل مغلقاً: غيابُ الدليل ليس دليلاً. وملفّ الجاهزيّة وحده يشهد للإقلاع
        # لا للحياة، فلا يُقبَل بديلاً عن النبضة.
        return False, "not ready: heartbeat file missing"
    age = now - HEARTBEAT_FILE.stat().st_mtime
    if age < -FUTURE_TOLERANCE_SEC:
        return False, f"not ready: heartbeat dated {int(-age)}s in the future"
    limit = effective_max_age()
    if age > limit:
        return False, f"not ready: heartbeat stale (age={int(age)}s > max={limit}s)"
    return True, f"ready (age={int(max(age, 0))}s max={limit}s)"


def main() -> int:
    ok, reason = check()
    print(reason)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

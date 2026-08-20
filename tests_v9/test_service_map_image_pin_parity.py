"""خريطة خدمات الدماغ تُعلِن صورةً لا تعمل عليها المنصّة — عطلٌ لا يُحمِّر شيئاً.

``SERVICE-MAP-IMAGE-PIN-DRIFTS-SILENTLY-01``. مقيسٌ على حزمتَي `V4` و`V5`: دلتا رفعت
وسم Ollama من ``0.3.14`` إلى ``0.32.5@sha256:…`` في ``.env.example`` و
``docker-compose.v9.yml``، ثمّ **سقط السطر المقابل في**
``sahool-brain/architecture/service-map.md`` أثناء إعادة الإرساء فبقي على القديم —
**وبقي ساقطاً في `V5` أيضاً** بعد أن سُمّي، فليست زلّة مرّة واحدة.

**ولماذا هذا أسوأ من فشل:** لا مولّد يكتب هذا الملفّ (فليس ضمن مدى
``verify_all_generated``)، ولا اختبار كان يربطه بـcompose — بحثتُ فلم أجد. أي أنّ
الشجرة كانت ستمرّ **خضراء بالكامل** وهي تحمل تناقضاً في مصدرٍ يُقرأ لاحقاً على أنّه
المرجع. وقاعدة الدماغ الصارمة «لا معلومة بلا مصدر» تجعل الخطأ المُصدَّر أسوأ من
الغياب: يُقتبَس بثقة.

**والنطاق ضيّقٌ عمداً — تثبيتُ صورة واحدة، لا مطابقةُ الخريطة كلّها للـcompose.**
الخريطة وثيقةٌ بشريّة تصف وتشرح، ومطابقتُها آليّاً بالكامل تُحوّلها إلى مصنوعة
مولَّدة وتقتل غرضها. المقيس هنا **ما درَّ فعلاً**: قيمة ``OLLAMA_IMAGE``.

يفشل مغلقاً: غيابُ أيّ من الملفّين أو غيابُ السطر إخفاقٌ مُسمّى، لا تخطٍّ.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.example"
COMPOSE = ROOT / "docker-compose.v9.yml"
SERVICE_MAP = ROOT / "sahool-brain/architecture/service-map.md"

_ENV_PIN = re.compile(r"^OLLAMA_IMAGE=(?P<image>\S+)\s*$", re.MULTILINE)


def _declared_pin() -> str:
    """المصدر الأعلى هو ``.env.example`` — منه يأخذ compose افتراضَه."""
    assert ENV.is_file(), f"{ENV} غير موجود — لا يُعرَف ما الصورة المُعلَنة"
    match = _ENV_PIN.search(ENV.read_text(encoding="utf-8"))
    assert match is not None, "لا سطر `OLLAMA_IMAGE=` في .env.example"
    return match.group("image")


def test_the_compose_default_matches_the_declared_pin():
    """``${OLLAMA_IMAGE:-…}`` نسخةٌ ثانية من القيمة — ونسختان تنحرفان."""
    assert COMPOSE.is_file(), f"{COMPOSE} غير موجود"
    pin = _declared_pin()
    assert f"${{OLLAMA_IMAGE:-{pin}}}" in COMPOSE.read_text(encoding="utf-8"), (
        "افتراض compose لا يطابق `OLLAMA_IMAGE` في .env.example — "
        "فمَن يشغّل بلا ملفّ بيئة يحصل على صورةٍ أخرى"
    )


def test_the_brain_service_map_names_the_same_image_the_platform_runs():
    """الفقد المقيس: الخريطة بقيت على ``0.3.14`` بينما المنصّة على ``0.32.5``."""
    assert SERVICE_MAP.is_file(), f"{SERVICE_MAP} غير موجود"
    pin = _declared_pin()
    text = SERVICE_MAP.read_text(encoding="utf-8")
    row = next((line for line in text.splitlines() if "`sahool-ollama`" in line), None)
    assert row is not None, "لا سطر لـ`sahool-ollama` في خريطة الخدمات"
    assert f"`{pin}`" in row, (
        "خريطة خدمات الدماغ تُعلِن صورةً غير التي تُشغّلها المنصّة.\n"
        f"  المُعلَن في .env.example : {pin}\n"
        f"  المكتوب في الخريطة      : {row.strip()}\n"
        "  الخريطة تُحرَّر يدويّاً — حدّثها، ولا يوجد `--fix` يفعل ذلك عنك."
    )

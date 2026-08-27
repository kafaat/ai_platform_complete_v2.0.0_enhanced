"""كلُّ مسارٍ يطلبه عميلُ الطقس مُعلَنٌ في الخدمة التي يناديها.

**العطلُ المقيس (P2):** `weather_service_client.get_tile_cache_stats` كان يطلب
`/v1/weather/tile-cache/stats`، و`weather-service/main.py` يُعلن
`/v1/weather/cache-stats` — ولا مسارَ بالاسم الأوّل في سطحِ الخدمة كلِّه. فكلُّ
نداءٍ كان يُنهي **404 حتماً**، لا احتمالاً.

**ولمَ لم يُمسَك بالاختبارات القائمة:** طرفا العقد يعيشان في خدمتين، وكلٌّ منهما
مختبَرٌ وحدَه. اختبارُ العميل يزيّف الاستجابة، واختبارُ الخدمة ينادي مسارَها
الصحيح — فيمرّ الطرفان خضراء والقفزةُ بينهما **لا يفحصها أحد**. وهذا الاختبارُ
هو الطرفُ الغائب: يقرأ السلاسلَ من الملفّين ويقابلها.

**وحدُّ صدقٍ يُقال:** هذا فحصٌ نصّيٌّ لا تشغيلٌ حيّ. لا يقيس أنّ الخدمة تستجيب،
بل أنّ المسارَ المطلوب **مُعلَنٌ** فيها. وهو بالضبط الصنفُ الذي أفلت — انحرافُ
سلسلةٍ نصّيّة بين طرفين لا يلتقيان في أيّ اختبار.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "services/sahool-platform/api/weather_service_client.py"
SERVICE_MAIN = ROOT / "services/weather-service/main.py"

# ما يطلبه العميل: أوّلُ وسيطٍ نصّيّ لكلّ `weather_get_json("/…")` أو `weather_post_json`.
_REQUESTED = re.compile(r'weather_(?:get|post)_json\(\s*(?:f?)"(/[^"]*)"')
# ما تُعلنه الخدمة: `app.get("/…")` / `app.post("/…")`.
_DECLARED = re.compile(r'^app\.(?:get|post)\("([^"]+)"\)', re.M)

# مقاطعُ المسار المتغيّرة تُطبَّع كي يُقارَن الشكلُ لا القيمة.
_PARAM = re.compile(r"\{[^}]+\}")


def _shape(path: str) -> str:
    return _PARAM.sub("{}", path.split("?", 1)[0].rstrip("/"))


def _requested() -> set[str]:
    return {_shape(m) for m in _REQUESTED.findall(CLIENT.read_text(encoding="utf-8"))}


def _declared() -> set[str]:
    return {_shape(m) for m in _DECLARED.findall(SERVICE_MAIN.read_text(encoding="utf-8"))}


@pytest.mark.unit
def test_the_reader_actually_found_both_sides() -> None:
    """فحصٌ يقرأ صفراً يمرّ أخضر عن سؤالٍ لم يطرحه — يُغلَق قبل الفحص نفسه."""
    assert _requested(), "لم يُقرأ أيُّ مسارٍ من العميل — تغيّر شكلُ النداء والفحصُ صار أعمى"
    assert _declared(), "لم يُقرأ أيُّ مسارٍ من الخدمة — تغيّر شكلُ الإعلان والفحصُ صار أعمى"


@pytest.mark.unit
def test_no_client_path_is_absent_from_the_weather_service_surface() -> None:
    missing = sorted(_requested() - _declared())
    assert not missing, (
        "مساراتٌ يطلبها عميلُ الطقس ولا تُعلنها الخدمة (404 حتميّ): "
        f"{missing} — المُعلَن: {sorted(_declared())}"
    )


@pytest.mark.unit
def test_the_specific_regression_stays_closed() -> None:
    """المرساةُ المسمّاة: الاسمُ الخاطئ لا يعود، والصحيحُ مُعلَن."""
    declared = _declared()
    assert "/v1/weather/cache-stats" in declared
    assert "/v1/weather/tile-cache/stats" not in _requested(), (
        "عاد العميلُ إلى المسار الذي لا تُعلنه الخدمة"
    )

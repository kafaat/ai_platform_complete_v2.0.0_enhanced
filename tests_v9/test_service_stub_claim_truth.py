"""لا خدمة تصف نفسها «فارغة» وهي تخدم مسارات حيّة — WEATHER-SERVICE-STUB-DOCSTRING-DRIFT.

`services/weather-service/__init__.py` كان يقول إنّ الخدمة **stub فارغ بلا منطق**
ووظيفتها داخل المنصّة. الادّعاء صحّ يوم كُتِب ثمّ صار كاذباً، بينما
`scripts/ci/weather_service_real_contract_gate.py` **يفرض عكسه** (يرفض 501 و
`implemented_runtime: False`). حارس حيّ يناقض توثيقاً بائتاً أسوأ من غياب التوثيق:
القارئ يصدّق النصّ ويبني عليه قراراً (دمج/حذف الخدمة).

وتصحيح النصّ وحده كان سيترك الصنف مفتوحاً. تعميمه إلى قاعدة كشف **الحالة الثانية
فوراً**: `indicators-service` يحمل الجملة **نفسها حرفيّاً** — نسخة كُتِبت مرّة
وانتشرت. لذلك القاعدة هنا لا الإصلاح.

القاعدة: ادّعاء «فارغ/بلا منطق/placeholder» في وصف حزمة خدمة يجب أن يطابق الشجرة.
خدمة تسجّل مسارات حيّة لا يجوز أن تصف نفسها فارغة.

حدّان مقصودان:
  • يُفحَص وصف الحزمة (`__init__.py`) وحده — لا كلّ تعليق في كلّ ملفّ — لأنّه الموضع
    الذي يقرأه من يسأل «ما هذه الخدمة؟».
  • **سرد التصحيح مسموح**: نصّ يذكر الادّعاء القديم ليشرح أنّه بطل ليس ادّعاءً به.
    التمييز بعلامة صريحة (`WEATHER-SERVICE-STUB-DOCSTRING-DRIFT`) لا بتخمين النيّة.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"

# ادّعاءات «لا منطق هنا» — بصيغها الواردة في المستودع وبالإنجليزيّة الشائعة.
_EMPTY_CLAIM = re.compile(
    r"stub\s*فارغ|بلا\s*منطق|empty\s+stub|no\s+logic|placeholder\s+only",
    re.IGNORECASE,
)

# علامة «هذا سرد تصحيح لا ادّعاء» — صريحة كي لا يُخمَّن القصد.
_CORRECTION_MARKER = "WEATHER-SERVICE-STUB-DOCSTRING-DRIFT"

# دليل منطق حيّ: تسجيل مسار بأيّ من الأسلوبين المستعملين في الشجرة.
_LIVE_ROUTE = re.compile(
    r"@(?:app|router)\.(?:get|post|put|delete|patch)\(|^app\.(?:get|post|put|delete|patch)\(",
    re.M,
)


def _service_packages() -> list[Path]:
    return sorted(p for p in SERVICES.glob("*/__init__.py") if p.is_file())


def _live_route_count(service_dir: Path) -> int:
    total = 0
    for py in service_dir.rglob("*.py"):
        if "__pycache__" in py.parts or "tests" in py.parts or py.name.startswith("test_"):
            continue
        try:
            total += len(_LIVE_ROUTE.findall(py.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return total


@pytest.mark.parametrize("init", _service_packages(), ids=lambda p: p.parent.name)
def test_no_service_calls_itself_empty_while_serving_routes(init: Path):
    """ادّعاء «فارغ» + مسارات حيّة = توثيق كاذب يُبنى عليه قرار خاطئ."""
    text = init.read_text(encoding="utf-8")
    claim = _EMPTY_CLAIM.search(text)
    if not claim:
        return
    if _CORRECTION_MARKER in text:
        return  # سرد تصحيح موسوم صراحةً، لا ادّعاء قائم
    routes = _live_route_count(init.parent)
    assert routes == 0, (
        f"{init.parent.name}: يصف نفسه «{claim.group(0)}» بينما يسجّل {routes} مساراً حيّاً — "
        "توثيق بائت يناقض الشجرة. صحّح الوصف أو أزِل المنطق."
    )


@pytest.mark.parametrize("name", ["weather-service", "indicators-service"])
def test_the_two_known_cases_are_corrected_and_stay_corrected(name: str):
    """الحالتان اللتان كشفتا القاعدة تُثبَّتان صراحةً كي لا تعودا."""
    text = (SERVICES / name / "__init__.py").read_text(encoding="utf-8")
    assert _CORRECTION_MARKER in text, f"{name}: وسم التصحيح مفقود"
    assert _live_route_count(SERVICES / name) > 0, (
        f"{name}: بلا مسارات حيّة — عندئذٍ التصحيح نفسه يحتاج مراجعة"
    )


def test_corrected_text_makes_no_certification_claim():
    """التصحيح لا يستبدل ادّعاءً بادّعاء: «مكتملة إنتاجيّاً» ليست بديلاً صادقاً.

    حالة الإنتاج تقرّرها بوّابات الصحّة/الجاهزيّة/الأدلّة، لا وصف الحزمة.
    """
    # النمط يستهدف **الادّعاء المُثبَت** لا مجرّد ذكر الكلمة: الصياغة الموصى بها
    # تحوي تنصّلاً صريحاً («does not by itself imply production certification»)،
    # فنمطٌ يرفض التنصّل يفحص الإملاء لا المعنى — وهو العيب نفسه الذي انتقدتُه في
    # الحارس النصّيّ. لذلك يُستثنى ما سبقته صيغة نفي.
    overclaim = re.compile(
        r"(?<!not )(?<!imply )(?:is\s+)?production[- ]ready|مكتملة\s*إنتاجيّاً|"
        r"production[- ]certified\b",
        re.IGNORECASE,
    )
    for name in ("weather-service", "indicators-service"):
        text = (SERVICES / name / "__init__.py").read_text(encoding="utf-8")
        hit = overclaim.search(text)
        assert hit is None, f"{name}: ادّعاء اعتماد إنتاجيّ في وصف الحزمة ({hit.group(0)!r})"


def test_corrected_text_embeds_no_countable_measurement():
    """ولا يُضمِّن أرقاماً تبلى: «١٩ وحدة/٤٧٤٩ سطراً» تصير كاذبة بأوّل إضافة.

    هذا بالضبط عطبُ النصّ الأصليّ في ثوب جديد — وكانت مسوّدتي الأولى تحمله.
    """
    counts = re.compile(r"\d{2,}\s*(?:وحدة|سطر|module|line|route|مسار)", re.IGNORECASE)
    for name in ("weather-service", "indicators-service"):
        text = (SERVICES / name / "__init__.py").read_text(encoding="utf-8")
        hit = counts.search(text)
        assert hit is None, f"{name}: قياس عدديّ مُضمَّن يبلى ({hit.group(0)!r})"

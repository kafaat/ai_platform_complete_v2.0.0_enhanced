"""حارس توجيه الطقس في nginx (وحدة) — يمنع انحدار `/api/weather/` إلى جذع 501.

السياق: منطق الطقس الحيّ (Open-Meteo + التخزين + الميزان المائيّ) يعيش في
`sahool-platform` على المسار `/api/v1/weather/*`. خدمة `weather-service` المستقلّة
**جذع صادق يردّ 501** لأيّ مسار طقس. لذا أيّ بوّابة من «معماريّة المنصّة» (التي تُعرّف
upstream `platform_backend` نحو `sahool-platform`) يجب أن توجّه `/api/weather/` إلى
المنصّة الحيّة لا إلى الجذع/أيّ upstream طقس مستقلّ.

ملاحظة: بوّابة «المعماريّة الموحّدة» (`nginx.unified.conf`) معماريّة MCP مختلفة لا
تُعرّف `platform_backend` و`weather-mcp` فيها مزوّد طقس حقيقيّ — فتُستثنى من هذا الحارس.
"""

import re
from pathlib import Path

import pytest

NGINX_DIR = Path(__file__).resolve().parents[1] / "nginx"


def _conf_files() -> list[Path]:
    return sorted(NGINX_DIR.glob("*.conf"))


def _is_platform_arch(text: str) -> bool:
    """معماريّة المنصّة: تُعرّف upstream platform_backend نحو sahool-platform."""
    return "upstream platform_backend" in text and "sahool-platform" in text


def _weather_proxy_target(text: str) -> str | None:
    """يستخرج هدف proxy_pass لكتلة `location /api/weather/` (سطر واحد أو متعدّد)."""
    m = re.search(r"location\s+/api/weather/\s*\{(.*?)\}", text, re.DOTALL)
    if not m:
        return None
    pm = re.search(r"proxy_pass\s+([^;]+);", m.group(1))
    return pm.group(1).strip() if pm else None


_PLATFORM_CONFS = [p for p in _conf_files() if _is_platform_arch(p.read_text(encoding="utf-8"))]


@pytest.mark.unit
def test_some_platform_arch_conf_exists():
    """تأكيد أنّ الحارس فعّال: توجد بوّابة معماريّة منصّة واحدة على الأقلّ (v9/fixed)."""
    names = {p.name for p in _PLATFORM_CONFS}
    assert "nginx.v9.conf" in names, names
    assert "nginx.fixed.conf" in names, names


@pytest.mark.unit
@pytest.mark.parametrize("conf", _PLATFORM_CONFS, ids=lambda p: p.name)
def test_weather_routes_to_live_platform(conf: Path):
    """كلّ بوّابة معماريّة منصّة توجّه /api/weather/ إلى platform_backend/api/v1/weather/."""
    text = conf.read_text(encoding="utf-8")
    target = _weather_proxy_target(text)
    if target is None:
        pytest.skip(f"{conf.name}: لا كتلة /api/weather/")
    assert target.startswith("http://platform_backend"), (
        f"{conf.name}: /api/weather/ يجب أن يذهب إلى platform_backend (المنصّة الحيّة) "
        f"لا إلى جذع/upstream طقس مستقلّ — الهدف الحاليّ: {target}"
    )
    assert "/api/v1/weather" in target, (
        f"{conf.name}: يجب إعادة الكتابة إلى /api/v1/weather (عقد المنصّة) — {target}"
    )

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_nginx_exposes_exact_legacy_health_aliases():
    conf = read("nginx/nginx.v9.conf")
    assert "location = /api/indicators/readyz" in conf
    assert "proxy_pass http://indicators_backend/readyz" in conf
    assert "location = /api/weather/readyz" in conf
    assert "proxy_pass http://weather_backend/readyz" in conf
    assert "location = /api/vegetation/readyz" in conf
    assert "proxy_pass http://vegetation_backend/readyz" in conf


def _declared_router_paths() -> set[str]:
    """المسارات المُعلَنة في **أيّ** وحدة تحت ``api/routers/`` — من كائن الراوتر لا من نصّه.

    يُستورَد كلّ ما في الحزمة ويُقرأ ``router.routes``؛ فالتأكيد ينجو من انتقال المسار
    بين ملفّات الراوترات، ولا يعتمد على ``app.routes`` (APP-ROUTES-INTROSPECTION-COUPLING-01).
    """
    platform = ROOT / "services" / "sahool-platform"
    if str(platform) not in sys.path:
        sys.path.insert(0, str(platform))
    package = importlib.import_module("api.routers")
    paths: set[str] = set()
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"api.routers.{info.name}")
        router = getattr(module, "router", None)
        for route in getattr(router, "routes", []):
            path = getattr(route, "path", None)
            if path:
                paths.add(path)
    return paths


def test_platform_has_fallbacks_for_misrouted_legacy_health_and_vegetation_paths():
    """المسارات الاحتياطيّة **مُعلَنة فعلاً** — لا «مكتوبة في main.py».

    الصيغة السابقة كانت تقطع `api/main.py` بحثاً عن `@app.get("…")`. ذلك الملفّ صار
    **خالياً من المسارات بالعقد** (`p1_main_decomposition_guard` يرفض أيّ مُزخرِف مسار
    فيه)، فصار الاختبار يصف بنيةً نُقِضت عمداً: يفشل بينما الستّة قائمة كلّها في
    `api/routers/compat_gateway.py`. القياس هنا على كائن الراوتر، فينجو من النقلة
    التالية أيضاً.
    """
    declared = _declared_router_paths()
    for route in [
        "/api/indicators/readyz",
        "/api/weather/readyz",
        "/api/vegetation/readyz",
        "/api/agent/health",
        "/api/vegetation/v1/all_fields",
        "/api/vegetation/v1/analyze",
    ]:
        assert route in declared, f"مسار احتياطيّ غير مُعلَن في أيّ راوتر: {route}"

    routers = ROOT / "services" / "sahool-platform" / "api" / "routers"
    sources = "\n".join(p.read_text(encoding="utf-8") for p in routers.glob("*.py"))
    assert "VEGETATION_SERVICE_URL" in sources, "الوجهة الخلفيّة لم تعد مُعلَنة"
    assert "/v1/all_fields" in sources
    assert "/v1/analyze" in sources


def test_field_indicator_map_shows_availability_status_before_user_clicks_tiles():
    src = read("frontend/src/components/FieldIndicatorMap.tsx")
    assert 'aria-label="indicator availability status"' in src
    assert "جاري التحقق" in src
    assert "غير متاح" in src
    assert "متاح:" in src
    assert "tileUnavailableMessage" in src
    assert "user_message" in src
    assert "reason" in src

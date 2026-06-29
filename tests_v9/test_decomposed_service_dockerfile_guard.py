"""حارس: كلّ خدمة مُفكَّكة (لها router_registry.py + routers/) يجب أن ينسخ Dockerfileها
هاتين الوحدتين إلى الصورة — وإلّا تتعطّل عند الإقلاع بـModuleNotFoundError.

السبب (عطل إنتاجيّ حقيقيّ): تفكيك المسارات (#551/#557/#560…) أضاف
``router_registry.py`` + حزمة ``routers/`` لكلّ خدمة. ``main.py`` يستورد
``from router_registry import register_routers``. لكنّ بعض Dockerfileات تنسخ ملفّات
مفردة (``COPY services/<svc>/main.py``) لا المجلّد كلّه — فلا تُنسَخ الوحدات الجديدة ⇒
``ModuleNotFoundError: No module named 'router_registry'`` عند الإقلاع ⇒ الخدمة
unhealthy (تأكّد على auth/vegetation). الاختبارات تستورد main من مجلّد الخدمة فلا
تكتشفه؛ هذا الحارس يلتقطه ساكناً في CI.

القبول: Dockerfile إمّا (أ) ينسخ المجلّد كلّه (``COPY services/<svc>/ /app/`` أو
``COPY . /app``)، أو (ب) ينسخ ``router_registry.py`` **و** ``routers`` صراحةً.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_SERVICES = os.path.join(_ROOT, "services")


def _decomposed_services() -> list[str]:
    out = []
    for name in sorted(os.listdir(_SERVICES)):
        sdir = os.path.join(_SERVICES, name)
        if os.path.isfile(os.path.join(sdir, "router_registry.py")) and os.path.isdir(
            os.path.join(sdir, "routers")
        ):
            out.append(name)
    return out


def _dockerfile(svc: str) -> str | None:
    sdir = os.path.join(_SERVICES, svc)
    for cand in ("Dockerfile",):
        p = os.path.join(sdir, cand)
        if os.path.isfile(p):
            return p
    # أيّ Dockerfile* آخر
    for f in sorted(os.listdir(sdir)):
        if f.startswith("Dockerfile"):
            return os.path.join(sdir, f)
    return None


def test_there_are_decomposed_services():
    """شبكة أمان: نعثر على خدمات مُفكَّكة فعلاً (وإلّا الحارس فارغ بصمت)."""
    assert len(_decomposed_services()) >= 5, _decomposed_services()


@pytest.mark.parametrize("svc", _decomposed_services())
def test_dockerfile_ships_router_registry_and_routers(svc: str):
    df = _dockerfile(svc)
    assert df is not None, f"{svc}: لا Dockerfile"
    src = open(df, encoding="utf-8").read()
    # (أ) نسخ المجلّد كلّه؟
    whole = re.search(
        rf"COPY\s+(services/{re.escape(svc)}/?\s|\.\s)",
        src,
    )
    if whole:
        return
    # (ب) نسخ صريح لـrouter_registry + routers
    has_registry = "router_registry.py" in src
    has_routers = re.search(r"COPY\s+\S*routers/?\s", src) is not None
    assert has_registry and has_routers, (
        f"{svc}: Dockerfile لا ينسخ router_registry.py/routers — ستتعطّل الخدمة بـ"
        f"ModuleNotFoundError عند الإقلاع. أضِف:\n"
        f"  COPY services/{svc}/router_registry.py /app/router_registry.py\n"
        f"  COPY services/{svc}/routers/ /app/routers/"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

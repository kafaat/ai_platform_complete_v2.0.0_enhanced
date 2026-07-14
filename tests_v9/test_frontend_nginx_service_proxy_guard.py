"""حارس وكلاء خدمات بوّابة الواجهة التطويريّة (frontend/nginx.conf، منفذ 3003).

السبب (فجوة مُثبَتة): الواجهة (`api.ts`) تنادي قواعد خاصّة لبعض الخدمات
(`vegetationApi`/`indicatorsApi`/`weatherApi` + `kongApi` لـ`/api/agent/`،
`/api/guardrails/`). بلا كتل `location` صريحة لها في بوّابة 3003 تسقط إلى catch-all
`/api/` ⇒ `sahool-platform` لا يملك هذه المسارات (vegetation/agent/guardrails غير
موجودة، indicators/weather تحت `/api/v1/`) ⇒ 404 (يكسر الدردشة/الغطاء/المؤشّرات/الطقس).

هذا الحارس يُثبّت الإصلاح في CI:
  • المسارات الخمسة موجودة و**تسبق** catch-all `location /api/`.
  • أهداف proxy_pass تطابق تحويلات `nginx.v9.conf` (مصدر الحقيقة للإنتاج).
  • `auth_request` مسموح **حصراً** في بوّابة الراستر (`/api/raster/` + `/_auth_verify`)
    — بلاطات <img> للحزمة الإنتاجية تحتاج عقد الهوية الموثّق — ومحظور في بقيّة الوكلاء.
  • `/api/raster/` ما زال موجوداً وقبل catch-all.

مسح ساكن لملفّ الإعداد — لا تشغيل nginx.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_FRONTEND_NGINX = os.path.join(_ROOT, "frontend", "nginx.conf")
_V9_NGINX = os.path.join(_ROOT, "nginx", "nginx.v9.conf")

# الخدمات التي يجب أن تُوكَّل صراحةً قبل catch-all + هدفها (جزء مميِّز من proxy_pass).
_REQUIRED = {
    "/api/vegetation/": "sahool-vegetation-analysis:8000/",
    "/api/indicators/": "sahool-platform:8000/api/v1/indicators/",
    "/api/weather/": "sahool-platform:8000/api/v1/weather/",
    "/api/agent/": "sahool-supervisor-agent:8000/agent/",
    "/api/guardrails/": "sahool-guardrails-engine:8000/",
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_frontend_nginx_exists():
    assert os.path.exists(_FRONTEND_NGINX), "frontend/nginx.conf مفقود"


def test_service_locations_present_and_before_catchall():
    """كلّ مسار خدمة موجود كـ`location ^~` ويسبق catch-all `location /api/`."""
    src = _read(_FRONTEND_NGINX)
    catchall = src.find("location /api/ {")
    assert catchall != -1, "catch-all `location /api/` غير موجود"
    for path in _REQUIRED:
        loc = src.find(f"location ^~ {path}")
        assert loc != -1, f"كتلة `location ^~ {path}` مفقودة في بوّابة 3003"
        assert loc < catchall, f"`{path}` يقع بعد catch-all ⇒ يُعترَض ولا يصل الخدمة"


def test_proxy_targets_match_v9_transforms():
    """أهداف proxy_pass تطابق تحويلات الإنتاج (v1 للمؤشّرات/الطقس، /agent/ للوكيل)."""
    src = _read(_FRONTEND_NGINX)
    for path, target in _REQUIRED.items():
        assert (
            f"proxy_pass         http://{target}" in src or f"proxy_pass http://{target}" in src
        ), f"هدف proxy_pass لـ`{path}` لا يطابق المتوقَّع (`{target}`)"
    # health خاصّ للوكيل (تطابق نمط v9: /api/agent/health → /health)
    assert "location = /api/agent/health {" in src, "مسار صحّة الوكيل المنفصل مفقود"
    assert "sahool-supervisor-agent:8000/health" in src, "هدف صحّة الوكيل خاطئ"


def _block_span(src: str, header: str) -> tuple[int, int]:
    """(start,end) لموقع `header ... { ... }` عبر موازنة الأقواس."""
    start = src.index(header)
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return start, j + 1
    raise AssertionError(f"unbalanced braces after {header!r}")


def test_auth_request_only_in_raster_dev_gateway():
    """auth_request مسموح **حصراً** داخل بوّابة الراستر (`/api/raster/` + `/_auth_verify`)
    ومحظور في بقيّة وكلاء التطوير (fetch APIs تُرسل Authorization/X-Tenant-Id مباشرةً).

    خلفيّة: بلاطة <img> للحزمة الإنتاجية لا تحمل tid/ترويسات ⇒ 403. أُصلِح بجعل
    `/api/raster/` يحاكي عقد الإنتاج (كوكي sahool_at ⇒ auth_request ⇒ X-Tenant-Id موثّق).
    هذا الحارس يسمح بذلك المسار الواحد ويمنع انحدار auth_request إلى بقيّة البوّابة.
    """
    src = _read(_FRONTEND_NGINX)
    verify_span = _block_span(src, "location = /_auth_verify")
    raster_span = _block_span(src, "location ^~ /api/raster/")

    def _allowed(pos: int) -> bool:
        return (verify_span[0] <= pos < verify_span[1]) or (raster_span[0] <= pos < raster_span[1])

    offenders = []
    for ln in src.splitlines():
        if ln.strip().startswith("#") or "auth_request" not in ln:
            continue
        if not _allowed(src.index(ln)):
            offenders.append(ln.strip())
    assert not offenders, f"auth_request خارج بوّابة الراستر (انحدار): {offenders}"


def test_raster_still_present_before_catchall():
    """انحدار: `/api/raster/` ما زال موجوداً (بـ`^~`) وقبل catch-all."""
    src = _read(_FRONTEND_NGINX)
    raster = src.find("location ^~ /api/raster/")
    catchall = src.find("location /api/ {")
    assert raster != -1 and raster < catchall, "`/api/raster/` مفقود أو بعد catch-all"


def test_v9_uses_same_path_transforms():
    """تأكيد مرجعيّ: nginx.v9.conf يحوّل indicators/weather إلى /api/v1/ والوكيل إلى /agent/."""
    if not os.path.exists(_V9_NGINX):
        pytest.skip("nginx.v9.conf غير موجود")
    v9 = _read(_V9_NGINX)
    assert "/api/v1/indicators/" in v9, "v9 لا يحوّل المؤشّرات إلى /api/v1/"
    assert "/api/v1/weather/" in v9, "v9 لا يحوّل الطقس إلى /api/v1/"
    assert "supervisor_backend/agent/" in v9, "v9 لا يوكّل الوكيل إلى /agent/"


def test_segmentation_routes_via_platform_with_long_timeout():
    """`/api/segmentation/` يُوكَّل **عبر المنصّة** (لا مباشرةً) بمهلة 120s.

    خدمة field-segmentation تتطلّب X-Agent-Token الذي تحقنه المنصّة فقط، فالتوجيه
    المباشر إليها يُرفَض. والتقطيع الآليّ/الهجين (SAM2-GPU) قد يتجاوز مهلة catch-all
    العامّة (60s)، فتلزم كتلة صريحة تسبق catch-all بمهلة قراءة أطول تطابق الإنتاج (120s).
    """
    src = _read(_FRONTEND_NGINX)
    loc = src.find("location ^~ /api/segmentation/")
    catchall = src.find("location /api/ {")
    assert loc != -1, "كتلة `location ^~ /api/segmentation/` مفقودة في بوّابة 3003"
    assert loc < catchall, "`/api/segmentation/` يقع بعد catch-all ⇒ يُعترَض بمهلة 60s"
    block = src[loc:catchall]
    assert "http://sahool-platform:8000/api/segmentation/" in block, (
        "التقطيع يجب أن يمرّ عبر المنصّة (حقن X-Agent-Token) لا مباشرةً إلى الخدمة"
    )
    assert "sahool-field-segmentation" not in block, (
        "توجيه مباشر إلى field-segmentation يتخطّى حقن التوكن ⇒ يُرفَض (401/403)"
    )
    assert "proxy_read_timeout    120s" in block or "proxy_read_timeout 120s" in block, (
        "التقطيع الآليّ قد يطول ⇒ يلزم proxy_read_timeout 120s (كـnginx.v9.conf)"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def test_client_max_body_size_covers_segmentation_snapshot() -> None:
    """413 على «تحديد حد الحقل تلقائيّ» (بلاغ 2026-07-04): لقطة SAM2 (~1.3MB) تجاوزت
    افتراضيّ nginx (1m) لغياب client_max_body_size من بوّابة 3003 بينما بوّابة
    الإنتاج (v9) حدّها 50M. الحارس يفرض وجود الحدّ في بوّابة التطوير بما لا يقلّ
    عن 12m (رفع صور الآفات في v9) — والمرآة الحاليّة 50M."""
    with open(_FRONTEND_NGINX, encoding="utf-8") as f:
        conf = f.read()
    import re

    m = re.search(r"client_max_body_size\s+(\d+)([mMkK])", conf)
    assert m, "client_max_body_size مفقود من frontend/nginx.conf — سيعود 413 التقطيع"
    size, unit = int(m.group(1)), m.group(2).lower()
    size_mb = size if unit == "m" else size / 1024
    assert size_mb >= 12, f"الحدّ {m.group(0)} أدنى من رفع صور الآفات (12m)"

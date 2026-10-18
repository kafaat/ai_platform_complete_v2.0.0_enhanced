import importlib.util
import re
from pathlib import Path

import pytest
from _nginx_contract import expand_upstream_targets

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "railway_frontend_readyz", ROOT / "deploy/railway/render_frontend.py"
)
_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_adapter)
_RAILWAY_ENV = {
    "SAHOOL_AUTH_UPSTREAM": "sahool-auth-main.railway.internal:8000",
    "SAHOOL_PLATFORM_UPSTREAM": "sahool-platform.railway.internal:8000",
}


def _text(path: str) -> str:
    conf = (ROOT / path).read_text(encoding="utf-8")
    return expand_upstream_targets(conf) if path == "frontend/nginx.conf" else conf


def test_frontend_gateway_exact_operational_routes_precede_spa() -> None:
    text = _text("frontend/nginx.conf")
    ready = text.index("location = /readyz {")
    identity = text.index("location = /runtime-identity {")
    spa = text.index("location / {", identity)
    assert ready < spa and identity < spa
    assert "sahool-platform:8000/runtime-identity" in text


# ── FRONTEND-READYZ-IMPERSONATES-PLATFORM-READINESS-01 ──────────────────────────
# `/readyz` في بوّابة الواجهة كان يُمرِّر إلى `/readyz` المنصّة: جاهزيّةٌ مُنتحَلة تُجمِّد
# نشر الواجهة عند عطل المنصّة. الشاهد يقيس المصدرَ والناتجَ المُصيَّر لـRailway: كتلة
# `location = /readyz` واحدة، تُجيب من nginx نفسه (`return`) ولا تُمرِّر إلى أيّ خلفيّة.
_PASS = re.compile(r"\b(?:proxy|fastcgi|uwsgi|scgi|grpc|memcached)_pass\b")


def _location_body(conf: str, args: str) -> str:
    """جسم `location <args> { … }` بمطابقة الأقواس (الكتلة تحوي `if { … }` متداخلة)."""
    uncommented = re.sub(r"#[^\n]*", "", conf)
    heads = [m.end() for m in re.finditer(rf"\blocation\s+{re.escape(args)}\s*\{{", uncommented)]
    assert len(heads) == 1, f"متوقَّع `location {args}` واحدة، وُجد {len(heads)}"
    depth, i = 1, heads[0]
    while depth:
        depth += {"{": 1, "}": -1}.get(uncommented[i], 0)
        i += 1
    return uncommented[heads[0] : i - 1]


def _assert_readyz_is_the_gateways_own(conf: str) -> None:
    body = _location_body(conf, "= /readyz")
    assert not _PASS.search(body), (
        "/readyz في بوّابة الواجهة يُمرِّر إلى خلفيّة — جاهزيّة المنصّة مُنتحَلة "
        "(FRONTEND-READYZ-IMPERSONATES-PLATFORM-READINESS-01)"
    )
    assert "platform" not in body, "/readyz يذكر المنصّة — ليس جاهزيّة البوّابة وحدها"
    ready = re.search(r"\breturn\s+200\s+'([^']*)'\s*;", body)
    assert ready, "/readyz لا يُجيب 200 من nginx نفسه"
    assert '"status":"ready"' in ready[1] and '"component":"frontend-gateway"' in ready[1]
    assert re.search(r"if\s*\(\s*!-f\s+\$document_root/index\.html\s*\)", body), (
        "/readyz لا يقيس أنّ قشرة SPA تُقدَّم"
    )
    assert re.search(r"\breturn\s+503\b", body), "/readyz بلا فرع «غير جاهز»"
    assert "limit_req" not in body, "مسبار جاهزيّة مُقيَّد يُسقط الخدمة زوراً"


@pytest.mark.parametrize("variant", ["source", "railway_rendered"])
def test_frontend_gateway_readyz_reports_the_gateway_not_the_platform(variant: str) -> None:
    conf = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    if variant == "railway_rendered":
        conf = _adapter.render(conf, _RAILWAY_ENV, ["10.0.0.2"])
    _assert_readyz_is_the_gateways_own(conf)


def test_readyz_witness_rejects_the_platform_proxied_shape() -> None:
    """التكذيب: شكل ما قبل الإصلاح (وكيل إلى `/readyz` المنصّة) يجب أن يُرفض."""
    prior = (
        "server {\n    location = /readyz {\n"
        "        proxy_pass         http://frontend_platform/readyz;\n"
        "        proxy_redirect http://sahool-platform:8000/readyz /readyz;\n"
        "        proxy_intercept_errors off;\n    }\n}\n"
    )
    with pytest.raises(AssertionError, match="IMPERSONATES"):
        _assert_readyz_is_the_gateways_own(prior)


def test_production_gateway_is_private_and_never_spa_fallback() -> None:
    text = _text("nginx/nginx.v9.conf")
    ready = text.index("location = /readyz {")
    identity = text.index("location = /runtime-identity {")
    spa = text.index("location / {", identity)
    assert ready < spa and identity < spa
    for segment in (text[ready:identity], text[identity:spa]):
        assert "deny all;" in segment
        assert "proxy_intercept_errors off;" in segment
    assert "platform_backend/readyz" in text
    assert "platform_backend/runtime-identity" in text


def test_contract_forbids_html_fallback() -> None:
    text = _text("docs/architecture/GATEWAY_OPERATIONAL_ENDPOINT_CONTRACT.md")
    assert "`200 text/html` is forbidden" in text
    assert "private/operator-only" in text

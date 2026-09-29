"""A real instrumented request must reach the configured span exporter."""

import socket
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.tracing import configure_tracing
from tests_v9.service_module import _GENERIC_ROOTS, load_service_main, purge_generic_modules

pytestmark = pytest.mark.unit

AUTH_DIR = Path(__file__).resolve().parents[1] / "services" / "auth"


def test_unconfigured_app_does_not_claim_a_provider(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    app = FastAPI()
    assert not configure_tracing(app, "unit")
    assert not hasattr(app.state, "sahool_tracer_provider")


def test_request_exports_named_service_span(monkeypatch):
    from opentelemetry.exporter.otlp.proto.http import trace_exporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_on")
    exporter = InMemorySpanExporter()
    endpoints = []

    def factory(*, endpoint):
        endpoints.append(endpoint)
        return exporter

    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", factory)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    app = FastAPI()

    @app.get("/unit")
    def unit():
        return {"ok": True}

    assert configure_tracing(app, "sahool-unit")
    with TestClient(app) as client:
        assert client.get("/unit").status_code == 200
        assert app.state.sahool_tracer_provider.force_flush()
        spans = exporter.get_finished_spans()
        assert any(
            s.name == "GET /unit" and s.resource.attributes["service.name"] == "sahool-unit"
            for s in spans
        )
    assert endpoints == ["http://collector:4318/v1/traces"]


# ── AUTH-NO-TRACING-01 ────────────────────────────────────────────────────────
# كانت `services/sahool-platform/api/main.py` وحدها تستدعي `configure_tracing`، فمسارُ الدخول
# (sahool-auth) غائبٌ عن كلّ أثر. والقيدُ هنا أنّ auth هي مسارُ الدخول: غيابُ النقطة لا يفعل
# شيئاً، ومُجمِّعٌ لا يُبلَغ لا يُسقِط طلباً ولا إقلاعاً.


@pytest.fixture
def fresh_auth(monkeypatch):
    """`services/auth/main.py` مُستورَدةٌ من جديد (الاستدعاءُ عند الاستيراد هو المقيس)،
    ثمّ تُعاد وحداتُ الأسماء العامّة كما كانت كي لا يرث اختبارٌ لاحقٌ نسخةً ثانية (#927)."""
    saved = {k: v for k, v in sys.modules.items() if k.split(".")[0] in _GENERIC_ROOTS}
    saved_path = list(sys.path)
    monkeypatch.setenv("JWT_SECRET", "z" * 48)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_on")

    def load():
        purge_generic_modules()
        return load_service_main(str(AUTH_DIR), required_attrs=("app", "lifespan"))

    yield load
    purge_generic_modules()
    sys.modules.update(saved)
    sys.path[:] = saved_path


def test_auth_app_exports_its_own_spans(monkeypatch, fresh_auth):
    from opentelemetry.exporter.otlp.proto.http import trace_exporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    endpoints = []

    def factory(*, endpoint):
        endpoints.append(endpoint)
        return exporter

    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", factory)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://sahool-otel-collector:4318")
    auth = fresh_auth()
    provider = auth.app.state.sahool_tracer_provider
    # بلا `with`: لا lifespan ⇒ لا قاعدة ولا Redis؛ المقيس هو توصيلُ التتبّع لا الإقلاع.
    assert TestClient(auth.app).get("/health").status_code == 200
    assert provider.force_flush()
    spans = exporter.get_finished_spans()
    assert any(
        s.name == "GET /health" and s.resource.attributes["service.name"] == "sahool-auth"
        for s in spans
    ), [s.name for s in spans]
    assert endpoints == ["http://sahool-otel-collector:4318/v1/traces"]


def test_auth_starts_and_serves_without_otel_endpoint(monkeypatch, fresh_auth):
    """الإقلاعُ الحقيقيّ (lifespan) بلا نقطة OTLP — القاعدة وRedis وحدهما مُستبدَلان."""
    import shared.db_role_guard

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # مرفوضٌ فوراً ⇒ مسار التطوير
    auth = fresh_auth()
    assert not hasattr(auth.app.state, "sahool_tracer_provider")

    class _Pool:
        async def close(self):
            return None

    async def _create_pool(*_args, **_kwargs):
        return _Pool()

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth.asyncpg, "create_pool", _create_pool)
    monkeypatch.setattr(shared.db_role_guard, "assert_db_role_rls_safe", _noop)
    monkeypatch.setattr(auth, "_ensure_admin_user", _noop)
    with TestClient(auth.app) as client:
        assert client.get("/healthz").json()["status"] == "alive"
        assert client.get("/health").status_code == 200


def test_auth_unreachable_collector_never_blocks_login_path(monkeypatch, fresh_auth):
    """مُجمِّعٌ لا يُبلَغ (منفذٌ مغلق) بالمُصدِّر الحقيقيّ: الطلبات لا تنتظره، والإغلاق محدود.

    المقيس خارج الاختبار على `configure_tracing` نفسه (مهلة المُصدِّر الافتراضيّة 10ث):
    رفضُ اتّصال ⇒ إغلاقٌ في ~6.7ث، وعنوانٌ لا يُوجَّه ⇒ ~20ث — والطلبات ≤7ms في الحالتين.
    هنا تُقصَّر المهلة إلى 1ث كي لا يدفع الجناح ثمنَ ذلك الانتظار.
    """
    from opentelemetry.exporter.otlp.proto.http import trace_exporter

    real = trace_exporter.OTLPSpanExporter
    monkeypatch.setattr(
        trace_exporter, "OTLPSpanExporter", lambda *, endpoint: real(endpoint=endpoint, timeout=1)
    )
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{port}")
    auth = fresh_auth()
    provider = auth.app.state.sahool_tracer_provider
    client = TestClient(auth.app)
    started = time.monotonic()
    for _ in range(5):
        assert client.get("/health").status_code == 200
    assert time.monotonic() - started < 1.0, "الطلبات انتظرت المُجمِّع"
    started = time.monotonic()
    provider.shutdown()
    assert time.monotonic() - started < 5.0


def _otel_pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        spec = line.split("#", 1)[0].strip()
        if spec.startswith("opentelemetry-") and "==" in spec:
            name, _, version = spec.partition("==")
            pins[name.strip()] = version.strip()
    return pins


def test_auth_image_carries_the_platform_tracing_stack():
    """ضبطُ النقطة في compose وصورةٌ بلا الحزم ⇒ ImportError عند الإقلاع = الدخول ساقط.

    فالحزمُ تُثبَّت في متطلّبات auth بدبابيس المنصّة نفسها، و`shared/` (ومنه tracing.py)
    يُنسَخ إلى الصورة — الشرطان معاً، لأنّ أحدهما وحده يُسقِط الإقلاع لا التتبّع.
    """
    root = AUTH_DIR.parents[1]
    platform = _otel_pins(root / "services/sahool-platform/api/requirements.txt")
    assert {
        "opentelemetry-sdk",
        "opentelemetry-exporter-otlp-proto-http",
        "opentelemetry-instrumentation-fastapi",
    } <= set(platform)
    assert _otel_pins(AUTH_DIR / "requirements.txt") == platform
    dockerfile = (AUTH_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY shared/ /app/shared/" in dockerfile
    assert (root / "shared/tracing.py").is_file()


def test_auth_compose_exports_to_the_platform_collector():
    import yaml

    compose = AUTH_DIR.parents[1] / "docker-compose.v9.yml"
    services = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]
    key = "OTEL_EXPORTER_OTLP_ENDPOINT"
    assert (
        services["sahool-auth"]["environment"][key]
        == (services["sahool-platform"]["environment"][key])
    )
    assert "sahool-otel-collector" in services

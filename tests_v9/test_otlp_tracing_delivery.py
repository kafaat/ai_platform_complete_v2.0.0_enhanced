"""A real instrumented request must reach the configured span exporter."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.tracing import configure_tracing

pytestmark = pytest.mark.unit


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

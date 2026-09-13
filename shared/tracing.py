"""Explicit OTLP tracing for deployed HTTP services; no implicit cloud discovery."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit


def configure_tracing(app, service_name: str) -> bool:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be an HTTP(S) collector URL")

    # A configured exporter is required to be installed; do not report tracing
    # enabled while swallowing an ImportError or exporting to a no-op provider.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
    )
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls="healthz,readyz,metrics"
    )
    app.state.sahool_tracer_provider = provider
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(instance):
        try:
            async with original_lifespan(instance) as state:
                yield state
        finally:
            provider.shutdown()

    app.router.lifespan_context = lifespan
    return True

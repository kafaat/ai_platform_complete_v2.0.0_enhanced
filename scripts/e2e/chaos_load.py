#!/usr/bin/env python3
"""chaos_load.py — Chaos + Load harness خفيف بلا تبعيات.

الأهداف:
  - Load: قياس p95/error-rate لطلبات GET متزامنة.
  - Chaos: حقن latency وطلبات malformed وتحقق أن النظام لا ينهار.
  - لا يفترض k6/locust؛ يعمل بمكتبة Python القياسية فقط.

المتغيرات:
  BASE_URL=http://localhost
  LOAD_PATH=/api/v1/fields
  AUTH_TOKEN=<jwt اختياري>
  CONCURRENCY=20
  REQUESTS=200
  P95_MS=1500
  MAX_ERROR_RATE=0.02
  CHAOS_LATENCY_MS=250
  REQUIRE_LIVE_E2E=1  # يفشل عند غياب المكدس بدل SKIPPED
"""

from __future__ import annotations

import concurrent.futures
import os
import random
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from json import dumps


@dataclass(frozen=True)
class Result:
    status: int
    elapsed_ms: float
    error: str = ""


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.security.tls_policy import tls_context as _tls_context  # noqa: E402


def ssl_context():
    # INSECURE_TLS يُشرَّف فقط لأهداف loopback عبر المُعقِّم المركزيّ (shared.security.tls_policy).
    base = os.getenv("BASE_URL") or os.getenv("API_BASE") or "https://localhost"
    return _tls_context(base)


def reachable(base: str) -> bool:
    try:
        urllib.request.urlopen(
            urllib.request.Request(base.rstrip("/") + "/", method="GET"),
            timeout=5,
            context=ssl_context(),
        )  # noqa: S310
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
    return True


def call(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    token: str | None = None,
    chaos_latency_ms: int = 0,
) -> Result:
    if chaos_latency_ms > 0:
        time.sleep(random.uniform(0, chaos_latency_ms) / 1000.0)
    data = dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers=headers, method=method),
            timeout=float(os.getenv("E2E_TIMEOUT", "15")),
            context=ssl_context(),
        ) as resp:  # noqa: S310
            resp.read()
            return Result(resp.status, (time.perf_counter() - start) * 1000)
    except urllib.error.HTTPError as e:
        if e.fp:
            e.fp.read()
        return Result(e.code, (time.perf_counter() - start) * 1000, f"HTTP {e.code}")
    except Exception as e:
        return Result(0, (time.perf_counter() - start) * 1000, type(e).__name__)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("inf")
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round((pct / 100) * (len(values) - 1)))))
    return values[idx]


def main() -> int:
    base = os.getenv("BASE_URL", "http://localhost").rstrip("/")
    path = os.getenv("LOAD_PATH", "/api/v1/fields")
    url = base + path
    token = os.getenv("AUTH_TOKEN")
    total = int(os.getenv("REQUESTS", "200"))
    concurrency = int(os.getenv("CONCURRENCY", "20"))
    p95_budget = float(os.getenv("P95_MS", "1500"))
    max_error_rate = float(os.getenv("MAX_ERROR_RATE", "0.02"))
    chaos_latency_ms = int(os.getenv("CHAOS_LATENCY_MS", "250"))

    print(f"# chaos+load url={url} requests={total} concurrency={concurrency}")
    if not reachable(base):
        print("SKIPPED (no live stack)")
        return 1 if os.getenv("REQUIRE_LIVE_E2E") == "1" else 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [
            pool.submit(call, "GET", url, token=token, chaos_latency_ms=chaos_latency_ms)
            for _ in range(total)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futs)]

    # Chaos probes: malformed payload and impossible id should be controlled 4xx/401/403/422, not 5xx/timeout.
    probes = [
        call(
            "POST",
            base + os.getenv("FIELDS_PATH", "/api/v1/fields"),
            token=token,
            body={"geometry": {"type": "Polygon", "coordinates": []}},
        ),
        call(
            "PATCH",
            base + os.getenv("FIELDS_PATH", "/api/v1/fields") + "/missing-field",
            token=token,
            body={"base_version": -1},
        ),
    ]

    latencies = [r.elapsed_ms for r in results]
    error_count = sum(1 for r in results if r.status >= 500 or r.status == 0)
    error_rate = error_count / max(1, len(results))
    p50 = statistics.median(latencies) if latencies else float("inf")
    p95 = percentile(latencies, 95)
    probe_bad = [p for p in probes if p.status >= 500 or p.status == 0]

    print(f"LOAD p50_ms={p50:.1f} p95_ms={p95:.1f} error_rate={error_rate:.3%}")
    print("CHAOS probes=" + ", ".join(f"{p.status}/{p.elapsed_ms:.1f}ms" for p in probes))

    ok = True
    if p95 > p95_budget:
        print(f"FAIL p95 budget: {p95:.1f}ms > {p95_budget:.1f}ms")
        ok = False
    if error_rate > max_error_rate:
        print(f"FAIL error rate: {error_rate:.3%} > {max_error_rate:.3%}")
        ok = False
    if probe_bad:
        print("FAIL chaos probes produced 5xx/transport error: " + repr(probe_bad))
        ok = False
    if ok:
        print("PASS chaos+load gates")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

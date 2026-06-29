#!/usr/bin/env python3
"""SAHOOL Weather Engine runtime smoke checker.

Usage:
  python3 scripts/weather_runtime_smoke.py --base-url http://localhost:8000

The checker intentionally focuses on local/control-plane endpoints first. These
endpoints must work in Docker/Compose/Kubernetes even when Open-Meteo is down.
Real tile/operation endpoints are optional because they can legitimately return
429/502 depending on rate limits, network, and upstream availability.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Probe:
    path: str
    expected: tuple[int, ...]
    contains: tuple[str, ...] = ()
    timeout_s: float = 10.0


def _fetch(base_url: str, probe: Probe) -> tuple[int, str, float]:
    url = base_url.rstrip("/") + probe.path
    start = time.perf_counter()
    req = Request(url, headers={"Accept": "application/json,text/plain,*/*"})
    try:
        with urlopen(req, timeout=probe.timeout_s) as resp:  # noqa: S310 - operator supplied URL
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body, time.perf_counter() - start
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body, time.perf_counter() - start
    except URLError as exc:
        raise RuntimeError(f"connection failed for {url}: {exc}") from exc


def _default_probes(include_external: bool = False) -> list[Probe]:
    probes = [
        Probe("/api/v1/weather/readyz", (200, 503), ("weather-engine",)),
        Probe("/api/v1/weather/self-test", (200,), ("checks",)),
        Probe("/api/v1/weather/runtime-contract", (200,), ("frontend_contract",)),
        Probe("/api/v1/weather/env-doctor", (200,), ("checks",)),
        Probe("/api/v1/weather/runtime-smoke-plan", (200,), ("critical_endpoints",)),
        Probe("/api/v1/weather/layers", (200,), ("runtime-smoke-plan", "tile_interpolation")),
        Probe("/api/v1/weather/tile-cache/stats", (200,), ("items",)),
        Probe("/api/v1/weather/observability", (200,), ("requests",)),
        Probe("/api/v1/weather/metrics.prom", (200,), ("sahool_weather_cache_items",)),
    ]
    if include_external:
        probes.extend(
            [
                Probe(
                    "/api/v1/weather/tile-data/8/155/108?layer=temperature&time=now&model=best_match&interpolation=grid",
                    (200, 429, 502),
                ),
                Probe(
                    "/api/v1/weather/operation-plan?lat=15.37&lon=44.19&operations=spraying,irrigation&hours=0,3,6&model=best_match",
                    (200, 429, 502),
                ),
            ]
        )
    return probes


def run(base_url: str, probes: Iterable[Probe]) -> int:
    failures: list[dict] = []
    results: list[dict] = []
    for probe in probes:
        try:
            status, body, latency = _fetch(base_url, probe)
            ok = status in probe.expected and all(token in body for token in probe.contains)
            item = {
                "path": probe.path,
                "status": status,
                "expected": list(probe.expected),
                "latency_ms": round(latency * 1000, 2),
                "ok": ok,
            }
            if not ok:
                item["body_preview"] = body[:500]
                failures.append(item)
            results.append(item)
        except Exception as exc:  # noqa: BLE001 - CLI should report all probe errors
            item = {"path": probe.path, "ok": False, "error": str(exc)}
            failures.append(item)
            results.append(item)

    print(
        json.dumps(
            {"base_url": base_url, "ok": not failures, "results": results},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url", required=True, help="Base API URL, e.g. http://localhost:8000"
    )
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Also probe endpoints that may call Open-Meteo",
    )
    args = parser.parse_args()
    return run(args.base_url, _default_probes(args.include_external))


if __name__ == "__main__":
    sys.exit(main())

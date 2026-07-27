#!/usr/bin/env python3
"""Functional runtime probes — verify a service COMPUTES correctly, not just that
it is alive.

A health probe answers "is the process up?"; a functional probe answers "does the
real endpoint, given a known input, return a schema-conformant, plausible, and
deterministic result?". This is the honest evidence that should back a
``runtime_verified`` claim — health-liveness alone is not.

Two modes, deliberately separated so the repository stays at its honest baseline:

  --check  (CI-safe, no network): validate every plan's structure and that each
           probe points at a route the target service actually registers. Never
           runs a service, never emits evidence, never touches the runtime ledger.

  --run    (opt-in, needs the service running): execute each probe live against a
           base URL, assert expected status + response schema/value assertions +
           determinism, and write functional evidence. Producing evidence here does
           NOT by itself set runtime_verified — that remains a separate, reviewed step.

Scope: only ``dependency_class: compute-only`` probes are supported so a run needs
no DB/Redis/external provider. Extending to DB/provider-backed probes is future work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = ROOT / "runtime-verification" / "functional_probes"
EVIDENCE_DIR = ROOT / "runtime-verification" / "functional_evidence"
SCHEMA_VERSION = "1.0"
_ROUTE_RE = re.compile(r'app\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']')
_ALLOWED_DEPENDENCY = {"compute-only"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def registered_routes(entrypoint: Path) -> set[tuple[str, str]]:
    """(METHOD, path) pairs a FastAPI entrypoint registers via ``app.<method>(...)``."""
    if not entrypoint.exists():
        return set()
    text = entrypoint.read_text(encoding="utf-8", errors="ignore")
    return {(m.group(1).upper(), m.group(2)) for m in _ROUTE_RE.finditer(text)}


def validate_plan(plan: dict[str, Any], path: Path) -> list[str]:
    """Static validation: structure + every probe points at a real registered route.
    No network. Returns a list of human-readable errors (empty == valid)."""
    errors: list[str] = []
    for key in ("schema_version", "service", "entrypoint", "probes"):
        if key not in plan:
            errors.append(f"{path.name}: missing '{key}'")
    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{path.name}: schema_version must be {SCHEMA_VERSION}")
    routes = registered_routes(ROOT / str(plan.get("entrypoint", "")))
    probes = plan.get("probes", [])
    if not isinstance(probes, list) or not probes:
        errors.append(f"{path.name}: 'probes' must be a non-empty list")
        probes = []
    seen_ids: set[str] = set()
    for i, probe in enumerate(probes):
        tag = f"{path.name}:probe[{i}]"
        if not isinstance(probe, dict):
            errors.append(f"{tag}: not an object")
            continue
        pid = probe.get("probe_id")
        if not isinstance(pid, str) or not pid:
            errors.append(f"{tag}: missing probe_id")
        elif pid in seen_ids:
            errors.append(f"{tag}: duplicate probe_id {pid}")
        else:
            seen_ids.add(pid)
        method = str(probe.get("method", "")).upper()
        route = probe.get("path")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            errors.append(f"{tag}: invalid method {probe.get('method')!r}")
        if not isinstance(route, str) or not route.startswith("/"):
            errors.append(f"{tag}: invalid path {route!r}")
        elif routes and (method, route) not in routes:
            errors.append(f"{tag}: {method} {route} is not registered in {plan['entrypoint']}")
        if probe.get("dependency_class") not in _ALLOWED_DEPENDENCY:
            errors.append(
                f"{tag}: dependency_class must be one of {sorted(_ALLOWED_DEPENDENCY)} "
                "(only self-contained compute probes are supported)"
            )
        if not isinstance(probe.get("expected_status"), int):
            errors.append(f"{tag}: expected_status must be an int")
        for j, a in enumerate(probe.get("response_assertions", []) or []):
            if not isinstance(a, dict) or "field" not in a:
                errors.append(f"{tag}:assertion[{j}]: must be an object with 'field'")
            elif not any(k in a for k in ("type", "min", "max", "equals")):
                errors.append(f"{tag}:assertion[{j}]: needs at least one of type/min/max/equals")
    return errors


def _extract(payload: Any, dotted: str) -> tuple[bool, Any]:
    cur = payload
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def _check_assertion(payload: Any, a: dict[str, Any]) -> tuple[bool, str]:
    found, value = _extract(payload, a["field"])
    if not found:
        return False, f"{a['field']}: missing"
    if "type" in a:
        want = a["type"]
        ok = (
            (want == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
            or (want == "string" and isinstance(value, str))
            or (want == "boolean" and isinstance(value, bool))
            or (want == "array" and isinstance(value, list))
        )
        if not ok:
            return False, f"{a['field']}: type != {want} (got {type(value).__name__})"
    if "equals" in a:
        exp = a["equals"]
        if isinstance(exp, (int, float)) and isinstance(value, (int, float)):
            if abs(value - exp) > float(a.get("tolerance", 0.0)):
                return False, f"{a['field']}: {value} != {exp} (tol {a.get('tolerance', 0.0)})"
        elif value != exp:
            return False, f"{a['field']}: {value!r} != {exp!r}"
    if "min" in a and (not isinstance(value, (int, float)) or value < a["min"]):
        return False, f"{a['field']}: {value} < min {a['min']}"
    if "max" in a and (not isinstance(value, (int, float)) or value > a["max"]):
        return False, f"{a['field']}: {value} > max {a['max']}"
    return True, f"{a['field']}: ok"


def _http(base_url: str, probe: dict[str, Any], timeout: float) -> tuple[int, float, bytes]:
    method = str(probe["method"]).upper()
    url = base_url.rstrip("/") + probe["path"]
    body = probe.get("request_body")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — first-party probe
        raw = resp.read()
        status = resp.status
    return status, round((time.perf_counter() - start) * 1000, 3), raw


def run_probe(base_url: str, probe: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Execute one probe live and evaluate status + assertions + determinism."""
    failures: list[str] = []
    status, latency_ms, raw = _http(base_url, probe, timeout)
    if status != probe["expected_status"]:
        failures.append(f"status {status} != {probe['expected_status']}")
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        payload = None
        failures.append("response is not valid JSON")
    if payload is not None:
        for a in probe.get("response_assertions", []) or []:
            ok, detail = _check_assertion(payload, a)
            if not ok:
                failures.append(detail)
    determinism_ok = True
    if probe.get("deterministic"):
        _, _, raw2 = _http(base_url, probe, timeout)
        determinism_ok = hashlib.sha256(raw).hexdigest() == hashlib.sha256(raw2).hexdigest()
        if not determinism_ok:
            failures.append("non-deterministic: repeated identical request gave a different body")
    return {
        "probe_id": probe["probe_id"],
        "method": str(probe["method"]).upper(),
        "path": probe["path"],
        "http_status": status,
        "latency_ms": latency_ms,
        "deterministic": determinism_ok,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "status": "passed" if not failures else "failed",
        "failures": failures,
    }


def run_live(plan: dict[str, Any], base_url: str, environment_id: str, timeout: float) -> dict:
    results = [run_probe(base_url, p, timeout) for p in plan["probes"]]
    started = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "functional",
        "service": plan["service"],
        "environment_id": environment_id,
        "base_url": base_url,
        "generated_at": started,
        "all_passed": all(r["status"] == "passed" for r in results),
        "probe_results": results,
    }


def cmd_check() -> int:
    plans = sorted(PLAN_DIR.glob("*.json")) if PLAN_DIR.exists() else []
    if not plans:
        print("functional_probe_runner: no plans found", file=sys.stderr)
        return 1
    all_errors: list[str] = []
    for path in plans:
        all_errors.extend(validate_plan(_load(path), path))
    if all_errors:
        print("functional probe plan validation FAILED:", file=sys.stderr)
        for e in all_errors:
            print("  - " + e, file=sys.stderr)
        return 1
    total = sum(len(_load(p)["probes"]) for p in plans)
    print(f"functional_probe_runner_ok plans={len(plans)} probes={total} (static validation)")
    return 0


def cmd_run(service: str | None, base_url: str, environment_id: str, timeout: float) -> int:
    plans = sorted(PLAN_DIR.glob("*.json")) if PLAN_DIR.exists() else []
    selected = [p for p in plans if service is None or _load(p)["service"] == service]
    if not selected:
        print(f"no plan for service {service!r}", file=sys.stderr)
        return 1
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    rc = 0
    for path in selected:
        plan = _load(path)
        errs = validate_plan(plan, path)
        if errs:
            print(f"plan {path.name} invalid; refusing to run:", file=sys.stderr)
            for e in errs:
                print("  - " + e, file=sys.stderr)
            rc = 1
            continue
        evidence = run_live(plan, base_url, environment_id, timeout)
        out = EVIDENCE_DIR / f"{plan['service']}-{environment_id}.json"
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{plan['service']}: {'ALL PASS' if evidence['all_passed'] else 'FAIL'} -> {out}")
        for r in evidence["probe_results"]:
            mark = "PASS" if r["status"] == "passed" else "FAIL"
            print(f"  [{mark}] {r['probe_id']} {r['method']} {r['path']} http={r['http_status']}")
            for f in r["failures"]:
                print(f"        ! {f}")
        rc = rc or (0 if evidence["all_passed"] else 1)
    return rc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="static plan validation (CI-safe)")
    g.add_argument("--run", action="store_true", help="execute probes live against --base-url")
    p.add_argument("--service", default=None)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--environment-id", default="local")
    p.add_argument("--timeout", type=float, default=25.0)
    a = p.parse_args(argv)
    if a.check:
        return cmd_check()
    return cmd_run(a.service, a.base_url, a.environment_id, a.timeout)


if __name__ == "__main__":
    raise SystemExit(main())

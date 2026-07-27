#!/usr/bin/env python3
"""Strict functional probe runner. Produces signed, runtime-bound evidence only."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = ROOT / "runtime-verification/functional_probes"
EVIDENCE_DIR = ROOT / "runtime-verification/functional_evidence"
IDENTITY_MAP = ROOT / "runtime-verification/service_identity_map.json"
BRIDGE = ROOT / "scripts/ci/runtime_identity_bridge.py"
SCHEMA_VERSION = "1.0"
EVIDENCE_SCHEMA_VERSION = "2.0"
_ROUTE_RE = re.compile(r'(?:app|router)\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']')
_ALLOWED_DEPENDENCY = {"compute-only"}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ENV_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")
_ENV_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def registered_routes(entrypoint: Path):
    if not entrypoint.exists():
        return set()
    return {
        (m.group(1).upper(), m.group(2))
        for m in _ROUTE_RE.finditer(entrypoint.read_text(encoding="utf-8", errors="ignore"))
    }


def validate_plan(plan: dict[str, Any], path: Path) -> list[str]:
    e = []
    for k in ("schema_version", "service", "entrypoint", "probes"):
        if k not in plan:
            e.append(f"{path.name}: missing '{k}'")
    if plan.get("schema_version") != SCHEMA_VERSION:
        e.append(f"{path.name}: schema_version must be {SCHEMA_VERSION}")
    routes = registered_routes(ROOT / str(plan.get("entrypoint", "")))
    probes = plan.get("probes", [])
    if not isinstance(probes, list) or not probes:
        e.append(f"{path.name}: 'probes' must be a non-empty list")
        probes = []
    seen = set()
    for i, p in enumerate(probes):
        tag = f"{path.name}:probe[{i}]"
        if not isinstance(p, dict):
            e.append(f"{tag}: not an object")
            continue
        pid = p.get("probe_id")
        if not isinstance(pid, str) or not pid:
            e.append(f"{tag}: missing probe_id")
        elif pid in seen:
            e.append(f"{tag}: duplicate probe_id {pid}")
        else:
            seen.add(pid)
        method = str(p.get("method", "")).upper()
        route = p.get("path")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            e.append(f"{tag}: invalid method")
        if not isinstance(route, str) or not route.startswith("/"):
            e.append(f"{tag}: invalid path {route!r}")
        elif not routes:
            e.append(f"{tag}: no statically registered routes found in {plan.get('entrypoint')}")
        elif (method, route) not in routes:
            e.append(f"{tag}: {method} {route} is not registered in {plan['entrypoint']}")
        if "headers" in p and not isinstance(p["headers"], dict):
            e.append(f"{tag}: headers must be an object")
        if p.get("dependency_class") not in _ALLOWED_DEPENDENCY:
            e.append(f"{tag}: dependency_class must be compute-only")
        if not isinstance(p.get("expected_status"), int):
            e.append(f"{tag}: expected_status must be an int")
        assertions = p.get("response_assertions", [])
        if not isinstance(assertions, list) or not assertions:
            e.append(f"{tag}: response_assertions must be non-empty")
        else:
            for j, a in enumerate(assertions):
                if not isinstance(a, dict) or "field" not in a:
                    e.append(f"{tag}:assertion[{j}]: invalid")
                elif not any(k in a for k in ("type", "min", "max", "equals")):
                    e.append(f"{tag}:assertion[{j}]: not falsifiable")
    return e


def _extract(payload, dotted):
    cur = payload
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def _check_assertion(payload, a):
    ok, v = _extract(payload, a["field"])
    if not ok:
        return False, f"{a['field']}: missing"
    typ = a.get("type")
    if typ:
        good = (
            (typ == "number" and isinstance(v, (int, float)) and not isinstance(v, bool))
            or (typ == "string" and isinstance(v, str))
            or (typ == "boolean" and isinstance(v, bool))
            or (typ == "array" and isinstance(v, list))
        )
        if not good:
            return False, f"{a['field']}: type != {typ}"
    if "equals" in a:
        exp = a["equals"]
        if isinstance(exp, (int, float)) and isinstance(v, (int, float)):
            if abs(v - exp) > float(a.get("tolerance", 0)):
                return False, f"{a['field']}: {v} != {exp}"
        elif v != exp:
            return False, f"{a['field']}: {v!r} != {exp!r}"
    if "min" in a and (not isinstance(v, (int, float)) or v < a["min"]):
        return False, f"{a['field']}: below minimum"
    if "max" in a and (not isinstance(v, (int, float)) or v > a["max"]):
        return False, f"{a['field']}: above maximum"
    return True, "ok"


def _resolve_headers(probe):
    return {
        str(k): _ENV_REF_RE.sub(lambda m: os.environ.get(m.group(1), ""), str(v))
        for k, v in (probe.get("headers") or {}).items()
    }


def _http_raw(url, method="GET", body=None, headers=None, timeout=25.0):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data else {}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as ex:
        status = ex.code
        raw = ex.read()
    return status, round((time.perf_counter() - start) * 1000, 3), raw


def _http(base_url, probe, timeout):
    return _http_raw(
        base_url.rstrip("/") + probe["path"],
        str(probe["method"]).upper(),
        probe.get("request_body"),
        _resolve_headers(probe),
        timeout,
    )


def run_probe(base_url, probe, timeout):
    failures = []
    try:
        status, latency, raw = _http(base_url, probe, timeout)
    except (OSError, urllib.error.URLError, TimeoutError) as ex:
        return {
            "probe_id": probe["probe_id"],
            "method": str(probe["method"]).upper(),
            "path": probe["path"],
            "http_status": None,
            "latency_ms": None,
            "deterministic": False,
            "response_sha256": None,
            "status": "failed",
            "failures": [f"network_error:{type(ex).__name__}"],
        }
    if status != probe["expected_status"]:
        failures.append(f"status {status} != {probe['expected_status']}")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = None
        failures.append("response is not valid JSON")
    if payload is not None:
        for a in probe.get("response_assertions", []):
            ok, detail = _check_assertion(payload, a)
            if not ok:
                failures.append(detail)
    det = True
    if probe.get("deterministic"):
        try:
            _, _, raw2 = _http(base_url, probe, timeout)
            det = hashlib.sha256(raw).digest() == hashlib.sha256(raw2).digest()
        except Exception:
            det = False
        if not det:
            failures.append("non-deterministic response")
    return {
        "probe_id": probe["probe_id"],
        "method": str(probe["method"]).upper(),
        "path": probe["path"],
        "http_status": status,
        "latency_ms": latency,
        "deterministic": det,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "status": "passed" if not failures else "failed",
        "failures": failures,
    }


def _fetch_json(base_url, path, timeout):
    status, _, raw = _http_raw(base_url.rstrip("/") + path, timeout=timeout)
    if status != 200:
        raise ValueError(f"{path} returned HTTP {status}")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"{path} did not return object")
    return obj


def _load_deployment_identity(path, service, tested_sha):
    if not path:
        raise ValueError(
            "--deployment-manifest is required; image identity may not come from runtime env"
        )
    obj = _load(Path(path))
    entry = (obj.get("services") or {}).get(service)
    if not isinstance(entry, dict):
        raise ValueError(f"deployment manifest missing {service}")
    for k in ("service", "git_sha", "build_id", "image_digest"):
        if not isinstance(entry.get(k), str) or not entry[k]:
            raise ValueError(f"deployment identity missing {k}")
    if entry["service"] != service or entry["git_sha"] != tested_sha:
        raise ValueError("deployment identity mismatch")
    if not _DIGEST_RE.fullmatch(entry["image_digest"]):
        raise ValueError("deployment image digest must be sha256 plus 64 lowercase hex")
    return entry


def verify_live_contract(plan, base_url, timeout, tested_sha, deployment_manifest):
    identity = _fetch_json(base_url, plan.get("identity_path", "/runtime-identity"), timeout)
    for k in ("service", "git_sha", "build_id", "metadata_source"):
        if not isinstance(identity.get(k), str) or not identity[k]:
            raise ValueError(f"runtime identity missing {k}")
    if identity["service"] != plan["service"]:
        raise ValueError("runtime identity service mismatch")
    if identity["git_sha"] != tested_sha:
        raise ValueError("runtime git_sha does not match --tested-sha expectation")
    if identity.get("metadata_source") != "immutable-image-file":
        raise ValueError("runtime identity is not immutable build metadata")
    deployed = _load_deployment_identity(deployment_manifest, plan["service"], tested_sha)
    if deployed["build_id"] != identity["build_id"]:
        raise ValueError("running container build_id differs from deployment manifest")
    identity = {
        **identity,
        "image_digest": deployed["image_digest"],
        "image_digest_source": "docker-inspect-manifest",
    }
    openapi = _fetch_json(base_url, plan.get("openapi_path", "/openapi.json"), timeout)
    paths = openapi.get("paths", {})
    for p in plan["probes"]:
        methods = paths.get(p["path"], {}) if isinstance(paths, dict) else {}
        if str(p["method"]).lower() not in methods:
            raise ValueError(f"unreachable route in live OpenAPI: {p['method']} {p['path']}")
    return identity


def _canonical(obj):
    x = dict(obj)
    x.pop("attestation", None)
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _head_sha():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def run_live(
    plan,
    base_url,
    environment_id,
    timeout,
    tested_sha,
    deployment_manifest,
    issuer="sahool-staging-hmac",
):
    if not _ENV_ID_RE.fullmatch(environment_id):
        raise ValueError("invalid environment_id")
    identity = verify_live_contract(plan, base_url, timeout, tested_sha, deployment_manifest)
    started = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    results = [run_probe(base_url, p, timeout) for p in plan["probes"]]
    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": "functional",
        "service": plan["service"],
        "tested_sha": tested_sha,
        "environment_id": environment_id,
        "base_url": base_url,
        "generated_at": started,
        "run_id": os.environ.get("GITHUB_RUN_ID") or str(uuid.uuid4()),
        "runtime_identity": identity,
        "artifact_digests": {
            "probe_plan_sha256": _sha(PLAN_DIR / f"{plan['service']}.json"),
            "runner_sha256": _sha(Path(__file__)),
            "identity_map_sha256": _sha(IDENTITY_MAP),
            "bridge_sha256": _sha(BRIDGE),
        },
        "all_passed": all(r["status"] == "passed" for r in results),
        "probe_results": results,
    }
    key = os.environ.get("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY")
    if not key:
        raise ValueError(
            "SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY is required; unsigned evidence is forbidden"
        )
    evidence["attestation"] = {
        "issuer": issuer,
        "algorithm": "hmac-sha256",
        "signature": hmac.new(key.encode(), _canonical(evidence), hashlib.sha256).hexdigest(),
    }
    return evidence


def cmd_check():
    plans = sorted(PLAN_DIR.glob("*.json")) if PLAN_DIR.exists() else []
    if not plans:
        print("functional_probe_runner: no plans found", file=sys.stderr)
        return 1
    errors = []
    for p in plans:
        try:
            errors.extend(validate_plan(_load(p), p))
        except Exception as ex:
            errors.append(f"{p.name}: {ex}")
    if errors:
        print("functional probe plan validation FAILED:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    print(
        f"functional_probe_runner_ok plans={len(plans)} probes={sum(len(_load(p)['probes']) for p in plans)} (static validation)"
    )
    return 0


def cmd_run(
    service,
    base_url,
    environment_id,
    timeout,
    tested_sha,
    deployment_manifest,
    issuer="sahool-staging-hmac",
):
    selected = [
        p
        for p in sorted(PLAN_DIR.glob("*.json"))
        if service is None or _load(p)["service"] == service
    ]
    if not selected:
        print(f"no plan for service {service!r}", file=sys.stderr)
        return 1
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    rc = 0
    for p in selected:
        try:
            plan = _load(p)
            errs = validate_plan(plan, p)
            if errs:
                raise ValueError("; ".join(errs))
            ev = run_live(
                plan, base_url, environment_id, timeout, tested_sha, deployment_manifest, issuer
            )
            safe = environment_id
            out = (EVIDENCE_DIR / f"{plan['service']}-{safe}-{ev['run_id']}.json").resolve()
            if EVIDENCE_DIR.resolve() not in out.parents:
                raise ValueError("unsafe evidence path")
            out.write_text(json.dumps(ev, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{plan['service']}: {'ALL PASS' if ev['all_passed'] else 'FAIL'} -> {out}")
            rc |= 0 if ev["all_passed"] else 1
        except Exception as ex:
            print(f"{p.name}: refused: {ex}", file=sys.stderr)
            rc = 1
    return rc


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--run", action="store_true")
    p.add_argument("--service")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--environment-id", default="local")
    p.add_argument("--timeout", type=float, default=25)
    p.add_argument("--tested-sha")
    p.add_argument("--issuer", default="sahool-staging-hmac")
    p.add_argument("--deployment-manifest")
    a = p.parse_args(argv)
    return (
        cmd_check()
        if a.check
        else cmd_run(
            a.service,
            a.base_url,
            a.environment_id,
            a.timeout,
            a.tested_sha or _head_sha(),
            a.deployment_manifest,
            a.issuer,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

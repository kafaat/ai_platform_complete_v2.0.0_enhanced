#!/usr/bin/env python3
"""Execute one service's runtime probe plan and write tamper-evident evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "runtime-verification" / "generated" / "runtime_probe_plan.json"
EVIDENCE_DIR = ROOT / "runtime-verification" / "evidence"


def now() -> str:
    return datetime.now(UTC).isoformat()


def git_sha() -> str:
    explicit = os.getenv("TESTED_SHA")
    if explicit:
        return explicit
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def request(url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            code = response.status
        status = "passed" if 200 <= code < 300 else "failed"
        error = None
    except urllib.error.HTTPError as exc:
        body = exc.read()
        code = exc.code
        status = "failed"
        error = f"HTTP {exc.code}"
    except Exception as exc:
        body = b""
        code = None
        status = "failed"
        error = type(exc).__name__
    return {
        "status": status,
        "http_status": code,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "response_bytes": len(body),
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    item = next((s for s in plan["services"] if s["service"] == args.service), None)
    if not item:
        raise SystemExit(f"unknown service: {args.service}")
    base_url = args.base_url or os.getenv(item["base_url_env"])
    if not base_url:
        raise SystemExit(f"missing --base-url or {item['base_url_env']}")
    sha = git_sha()
    if not sha:
        raise SystemExit("unable to determine tested SHA; set TESTED_SHA")

    started_at = now()
    results = []
    for probe in item["probes"]:
        result = request(base_url.rstrip("/") + probe["path"], args.timeout)
        results.append({**probe, **result})
    evidence = {
        "schema_version": "1.0",
        "service": args.service,
        "tested_sha": sha,
        "environment_id": args.environment_id,
        "base_url_sha256": hashlib.sha256(base_url.encode()).hexdigest(),
        "started_at": started_at,
        "completed_at": now(),
        "plan_sha256": plan["plan_sha256"],
        "probe_results": results,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE_DIR / f"{args.service}.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    passed = bool(results) and all(r["status"] == "passed" for r in results)
    print(f"wrote {output.relative_to(ROOT)}: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

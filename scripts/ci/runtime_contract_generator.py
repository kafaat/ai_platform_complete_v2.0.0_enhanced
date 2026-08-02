#!/usr/bin/env python3
"""Generate deterministic repository-derived runtime contracts for SAHOOL services.

This is static evidence only. It does not claim that a route, metric, trace, or secret
is present in a live deployment.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "service_inventory.csv"
OUT_DIR = ROOT / "runtime-contracts" / "generated"
INDEX = OUT_DIR / "runtime_contracts.json"
SUMMARY = OUT_DIR / "runtime_contracts_summary.json"
REPORT = OUT_DIR / "RUNTIME_CONTRACTS_REPORT.md"
SCHEMA_VERSION = "1.0"

TEXT_SUFFIXES = {
    ".py",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".env",
    ".sh",
    ".js",
    ".ts",
    ".tsx",
}
EXCLUDED = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".next"}
ROUTE_RE = re.compile(
    r"(?:@\w+\.)?(?:get|post|put|patch|delete|api_route)\(\s*[rubf]*[\"']([^\"']+)[\"']", re.I
)
ENV_CALL_RE = re.compile(r"(?:os\.getenv|os\.environ\.get|getenv)\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']")
ENV_INDEX_RE = re.compile(r"os\.environ\[\s*[\"']([A-Z][A-Z0-9_]+)[\"']\s*\]")
# A variable read through a module constant is still a variable. The two regexes above
# only see a *literal* inside the call, so `os.getenv(_CLOUD_POLICY_ENV, "strict")` was
# invisible and CDSE_CLOUD_POLICY appeared in no contract while --check still passed —
# a completeness gate reporting completeness it did not have. These two capture the
# indirect form: an identifier passed to the call, resolved against the module-level
# constants below. A constant that is never passed to a read is never admitted, so the
# resolution stays as narrow as the literal case.
ENV_CALL_INDIRECT_RE = re.compile(
    r"(?:os\.getenv|os\.environ\.get|getenv)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,)]"
)
ENV_INDEX_INDIRECT_RE = re.compile(r"os\.environ\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*\]")
# Module-level `NAME = "ENV_VAR"` — the only bindings the indirect forms resolve against.
ENV_CONST_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[\"']([A-Z][A-Z0-9_]+)[\"']", re.M)
SETTING_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*[:=]", re.M)
METRIC_RE = re.compile(r"(?:Counter|Gauge|Histogram|Summary)\(\s*[\"']([^\"']+)[\"']")
TRACE_RE = re.compile(r"(?:start_as_current_span|start_span)\(\s*[\"']([^\"']+)[\"']")
SECRET_MARKERS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PRIVATE_KEY",
    "API_KEY",
    "ACCESS_KEY",
    "CREDENTIAL",
)
# RUNTIME-CONTRACT-KEY-SUFFIX-NOT-SECRET-01. The markers above are substrings, so a
# name had to contain PRIVATE_KEY/API_KEY/ACCESS_KEY to count. Bare `..._KEY` matched
# none of them, and ten signing and HMAC keys were published as ordinary configuration:
# FCM_SERVER_KEY, SEASON_EDGE_HMAC_KEY, DECISION_WORKER_ASSERTION_KEY among them. A
# contract that lists a signing key beside a log level is not merely untidy -- it is
# reporting the service's secret surface as smaller than it is.
#
# Fail closed: the suffix means key material, and the exemptions are declared with the
# source line that was read, never inferred from the name. Deliberately NOT a cleverer
# regex: MFA_ALLOW_DERIVED_KEY and MFA_AUDIT_HASH_KEY differ by one word in one service,
# and one is a boolean flag. A pattern that separated those two would be a pattern
# fitted to thirteen known names -- a list wearing a pattern's clothes, which decays the
# moment the fourteenth name arrives.
KEY_SUFFIXES = ("_KEY", "_KEYS")
NONSECRET_KEYS_FILE = ROOT / "docs" / "architecture" / "runtime_contract_nonsecret_keys.json"


def declared_nonsecret_keys() -> set[str]:
    """Names exempt from the ``*_KEY`` rule, read from their declaration.

    Missing or malformed file yields an empty set, so every ``*_KEY`` name classifies
    as a secret. Losing the exemptions must over-report secrets, never under-report
    them: the failure has to fall on the safe side of the question it answers.
    """
    try:
        data = json.loads(NONSECRET_KEYS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {
        str(e["name"]) for e in data.get("nonsecret", []) if isinstance(e, dict) and "name" in e
    }


def is_secret(name: str) -> bool:
    """A variable is a secret by marker, or by carrying a key suffix without exemption."""
    if any(marker in name for marker in SECRET_MARKERS):
        return True
    if name.endswith(KEY_SUFFIXES):
        return name not in declared_nonsecret_keys()
    return False


CONFIG_EXCLUDE = {"PATH", "HOME", "HOSTNAME", "PWD", "PYTHONPATH"}


def norm_service(name: str) -> str:
    return "erp-bridge" if name == "odoo-bridge" else name


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _mark(flag: bool) -> str:
    return "✓" if flag else "—"


def text_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    out: list[Path] = []
    for p in base.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED for part in p.parts):
            continue
        if p.stat().st_size > 2_000_000:
            continue
        out.append(p)
    return sorted(out)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def resolve_indirect_env(content: str) -> set[str]:
    """Env names read through a module constant rather than a literal.

    Resolution is deliberately one hop and same-file: a bare identifier passed to
    ``os.getenv``/``os.environ.get``/``os.environ[...]`` is looked up in that module's
    ``NAME = "ENV_VAR"`` bindings. Anything that does not resolve is dropped rather than
    guessed — inventing a name would be worse than the omission this repairs.
    """
    referenced = set(ENV_CALL_INDIRECT_RE.findall(content)) | set(
        ENV_INDEX_INDIRECT_RE.findall(content)
    )
    if not referenced:
        return set()
    constants = dict(ENV_CONST_RE.findall(content))
    return {constants[name] for name in referenced if name in constants}


def extract_env_names(content: str, filename: str = "") -> set[str]:
    """Every env name one file declares — the single seam the scan reads through.

    This exists as its own function so the indirect resolution can be held by a test at
    the level the scan actually uses. Asserting on ``resolve_indirect_env`` alone would
    stay green if that call were dropped from the scan, which is precisely the shape of
    the original defect: a capability present but never run.
    """
    names = set(ENV_CALL_RE.findall(content)) | set(ENV_INDEX_RE.findall(content))
    names |= resolve_indirect_env(content)
    # Pydantic settings often declare uppercase fields directly.
    if filename in {"config.py", "settings.py"}:
        names |= set(SETTING_RE.findall(content))
    return names


def classify_routes(routes: set[str]) -> dict[str, list[str]]:
    low = {r.lower(): r for r in routes}
    health = sorted(
        {
            orig
            for key, orig in low.items()
            if key.rstrip("/") in {"/health", "/healthz", "/live", "/livez", "/ping"}
            or "health" in key
        }
    )
    ready = sorted({orig for key, orig in low.items() if "ready" in key})
    metrics = sorted(
        {orig for key, orig in low.items() if "metric" in key or key.rstrip("/") == "/metrics"}
    )
    return {"health": health, "readiness": ready, "metrics": metrics}


def scan_service(row: dict[str, str]) -> dict[str, Any]:
    raw_name = row["service"]
    name = norm_service(raw_name)
    base = ROOT / "services" / raw_name
    files = text_files(base)
    routes: set[str] = set()
    envs: set[str] = set()
    metric_names: set[str] = set()
    trace_spans: set[str] = set()
    evidence: dict[str, set[str]] = {
        "routes": set(),
        "configuration": set(),
        "metrics": set(),
        "tracing": set(),
    }

    for path in files:
        content = read_text(path)
        if not content:
            continue
        found_routes = set(ROUTE_RE.findall(content))
        if found_routes:
            routes.update(found_routes)
            evidence["routes"].add(rel(path))
        found_env = extract_env_names(content, path.name)
        if found_env:
            envs.update(found_env)
            evidence["configuration"].add(rel(path))
        found_metrics = set(METRIC_RE.findall(content))
        if found_metrics or "prometheus_client" in content:
            metric_names.update(found_metrics)
            evidence["metrics"].add(rel(path))
        found_spans = set(TRACE_RE.findall(content))
        if found_spans or "opentelemetry" in content:
            trace_spans.update(found_spans)
            evidence["tracing"].add(rel(path))

    route_groups = classify_routes(routes)
    secrets = sorted(e for e in envs if is_secret(e))
    configuration = sorted(e for e in envs if e not in secrets and e not in CONFIG_EXCLUDE)
    dockerfile = ROOT / row.get("dockerfile", "") if row.get("dockerfile") else None
    requirements = ROOT / row.get("requirements", "") if row.get("requirements") else None

    contract: dict[str, Any] = {
        "service": name,
        "source_service": raw_name,
        "domain": row.get("domain", "unknown"),
        "contract_version": SCHEMA_VERSION,
        "static_repository_evidence_only": True,
        "entrypoint": row.get("main", ""),
        "container": {
            "dockerfile": rel(dockerfile) if dockerfile and dockerfile.exists() else None,
            "requirements": rel(requirements) if requirements and requirements.exists() else None,
        },
        "endpoints": {
            "health": route_groups["health"],
            "readiness": route_groups["readiness"],
            "metrics": route_groups["metrics"],
        },
        "observability": {
            "metric_names": sorted(metric_names),
            "trace_spans": sorted(trace_spans),
            "metrics_instrumented": bool(metric_names or evidence["metrics"]),
            "tracing_instrumented": bool(trace_spans or evidence["tracing"]),
        },
        "configuration": configuration,
        "secrets": secrets,
        "evidence_paths": {key: sorted(value) for key, value in evidence.items()},
        "completeness": {},
    }
    gates = {
        "entrypoint": bool(contract["entrypoint"] and (ROOT / contract["entrypoint"]).exists()),
        "dockerfile": contract["container"]["dockerfile"] is not None,
        "health": bool(contract["endpoints"]["health"]),
        "readiness": bool(contract["endpoints"]["readiness"]),
        "metrics_endpoint_or_instrumentation": bool(
            contract["endpoints"]["metrics"] or contract["observability"]["metrics_instrumented"]
        ),
        "tracing_instrumentation": contract["observability"]["tracing_instrumented"],
        "configuration_declared": bool(configuration or secrets),
    }
    contract["completeness"] = {
        "gates": gates,
        "passed": sum(gates.values()),
        "total": len(gates),
        "score_pct": round(100 * sum(gates.values()) / len(gates), 1),
    }
    return contract


def load_inventory() -> list[dict[str, str]]:
    with INVENTORY.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build() -> tuple[dict[str, Any], dict[str, Any], str]:
    contracts = sorted((scan_service(row) for row in load_inventory()), key=lambda c: c["service"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_from": "service_inventory.csv + repository static scan",
        "static_repository_evidence_only": True,
        "services": contracts,
    }
    total = len(contracts)

    def count(pred):
        return sum(1 for c in contracts if pred(c))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "services": total,
        "with_health": count(lambda c: bool(c["endpoints"]["health"])),
        "with_readiness": count(lambda c: bool(c["endpoints"]["readiness"])),
        "with_metrics": count(
            lambda c: bool(c["endpoints"]["metrics"] or c["observability"]["metrics_instrumented"])
        ),
        "with_tracing": count(lambda c: c["observability"]["tracing_instrumented"]),
        "with_declared_configuration": count(lambda c: bool(c["configuration"] or c["secrets"])),
        "complete_static_contracts": count(
            lambda c: c["completeness"]["passed"] == c["completeness"]["total"]
        ),
        "live_runtime_verified": 0,
        "lowest_completeness": [
            {"service": c["service"], "score_pct": c["completeness"]["score_pct"]}
            for c in sorted(
                contracts, key=lambda c: (c["completeness"]["score_pct"], c["service"])
            )[:10]
        ],
    }
    lines = [
        "# SAHOOL Runtime Contract Inventory",
        "",
        "> Static repository evidence only. This report does not prove live runtime behavior.",
        "",
        "## Summary",
        "",
        f"- Services: **{total}**",
        f"- Health contract: **{summary['with_health']}**",
        f"- Readiness contract: **{summary['with_readiness']}**",
        f"- Metrics endpoint or instrumentation: **{summary['with_metrics']}**",
        f"- Tracing instrumentation: **{summary['with_tracing']}**",
        f"- Declared configuration/secrets: **{summary['with_declared_configuration']}**",
        f"- Complete static contracts: **{summary['complete_static_contracts']}**",
        "- Live runtime verified: **0**",
        "",
        "## Per-service completeness",
        "",
        "| Service | Score | Health | Ready | Metrics | Tracing | Config |",
        "|---|---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    for c in contracts:
        g = c["completeness"]["gates"]
        lines.append(
            f"| {c['service']} | {c['completeness']['score_pct']:.1f}% | {_mark(g['health'])} | {_mark(g['readiness'])} | {_mark(g['metrics_endpoint_or_instrumentation'])} | {_mark(g['tracing_instrumentation'])} | {_mark(g['configuration_declared'])} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "A missing static signal is a repository gap or an extraction limitation. A present signal is not production proof; live certification still requires observed responses, telemetry, and deployment evidence.",
        "",
    ]
    return payload, summary, "\n".join(lines)


def write_outputs(payload: dict[str, Any], summary: dict[str, Any], report: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(canonical_json(payload), encoding="utf-8")
    SUMMARY.write_text(canonical_json(summary), encoding="utf-8")
    REPORT.write_text(report, encoding="utf-8")


def check_outputs(payload: dict[str, Any], summary: dict[str, Any], report: str) -> int:
    expected = {INDEX: canonical_json(payload), SUMMARY: canonical_json(summary), REPORT: report}
    drift = [
        rel(path)
        for path, content in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]
    if drift:
        print("runtime_contract_drift_detected")
        for item in drift:
            print(f" - {item}")
        return 1
    print("runtime_contracts: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not INVENTORY.exists():
        raise SystemExit(f"missing inventory: {INVENTORY}")
    payload, summary, report = build()
    if args.generate:
        write_outputs(payload, summary, report)
        print(
            f"runtime_contracts_generated services={summary['services']} complete={summary['complete_static_contracts']}"
        )
        return 0
    return check_outputs(payload, summary, report)


if __name__ == "__main__":
    raise SystemExit(main())

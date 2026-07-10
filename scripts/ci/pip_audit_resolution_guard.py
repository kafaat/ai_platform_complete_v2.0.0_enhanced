#!/usr/bin/env python3
"""Guard against pip-audit dry-run resolver conflicts on shared packages.

GitHub Actions runs one critical pip-audit command with many requirements files in a
single resolver environment. Direct pins for the same package must therefore agree
for packages shared across those files. This guard is intentionally narrow: it
checks the known shared resolver-sensitive package set first (Redis) and reports the
files that would make pip-audit fail before the audit can even start.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Keep in sync with .github/workflows/ci.yml pip-audit critical path plus tests/dev
# files that are co-installed in other jobs with platform requirements.
REQ_FILES = [
    "services/sahool-platform/api/requirements.txt",
    "services/auth/requirements.txt",
    "services/guardrails-engine/requirements.txt",
    "requirements_real.txt",
    "services/actuator-service/requirements.txt",
    "services/agriai-engine/requirements.txt",
    "services/edge-inference/requirements.txt",
    "services/indicators-service/requirements.txt",
    "services/mcp_servers/requirements.txt",
    "services/odoo-bridge/requirements.txt",
    "services/qdrant-seed/requirements.txt",
    "services/raster-service/requirements.txt",
    "services/soil-service/requirements.txt",
    "services/supervisor-agent/requirements.txt",
    "services/tts-service/requirements.txt",
    "services/vegetation-analysis-service/requirements.txt",
    "services/video-processor/requirements.txt",
    "services/weather-service/requirements.txt",
    "tests_v9/requirements-test.txt",
    "requirements-dev.txt",
]

# لكلّ حزمة مشتركة: الإصدار المرجعيّ الذي تُثبّته المنصّة (==). بقيّة الملفّات يكفيها
# التوافق معه (مدى يقبله) — اتّفاقيّة CLAUDE.md للمسار الحرج: >= لا == حيث أمكن؛
# ResolutionImpossible ينشأ فقط من مواصفات متنافية، لا من المدى المتوافق.
SHARED_SINGLETONS = {
    "redis": "5.3.1",
}

REQ_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(?P<op>==|>=|<=|~=|>|<)\s*(?P<version>[^;\s#]+)"
)


def normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def meaningful(raw: str) -> str:
    return raw.split("#", 1)[0].strip()


def collect() -> dict[str, list[tuple[str, int, str, str]]]:
    found: dict[str, list[tuple[str, int, str, str]]] = {pkg: [] for pkg in SHARED_SINGLETONS}
    for rel in REQ_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        for line_no, raw in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            req = meaningful(raw)
            if not req or req.startswith("-"):
                continue
            m = REQ_RE.match(req)
            if not m:
                continue
            package = normalize(m.group("name"))
            if package in found:
                found[package].append((rel, line_no, m.group("op"), m.group("version")))
    return found


def check() -> None:
    errors: list[str] = []
    found = collect()
    for package, expected_version in SHARED_SINGLETONS.items():
        entries = found.get(package, [])
        if not entries:
            continue
        # يفشل الحلّ المُوحَّد فقط عند التنافي: تثبيت مختلف (==X≠المرجع) أو سقف/مدى
        # يستثني الإصدار المرجعيّ. المدى المتوافق (>=5.0.0 مثلاً) صالح ولا يُعاد تثبيته.
        exp = tuple(int(x) for x in expected_version.split("."))

        def _incompatible(op: str, ver: str, exp: tuple[int, ...] = exp) -> bool:
            try:
                v = tuple(int(x) for x in re.split(r"[^0-9]+", ver.strip()) if x != "")[:3]
            except ValueError:
                return True
            if op == "==":
                return v != exp
            if op == ">=":
                return v > exp
            if op == ">":
                return v >= exp
            if op == "<=":
                return v < exp
            if op == "<":
                return v <= exp
            if op == "~=":
                return v[: len(v) - 1] != exp[: len(v) - 1] or v > exp
            return True

        bad = [
            (rel, line_no, op, ver) for rel, line_no, op, ver in entries if _incompatible(op, ver)
        ]
        if bad:
            detail = "; ".join(
                f"{rel}:{line_no} has {package}{op}{ver}" for rel, line_no, op, ver in bad
            )
            errors.append(
                f"{package} specs must all admit the platform reference {package}=={expected_version} "
                f"(unified pip-audit resolver); incompatible: {detail}"
            )
    if errors:
        raise SystemExit("\n".join(errors))


def main() -> None:
    check()
    print("pip_audit_resolution_guard_ok")


if __name__ == "__main__":
    main()

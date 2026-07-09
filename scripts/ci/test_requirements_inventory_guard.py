#!/usr/bin/env python3
"""Guard the tests_v9 Python dependency contract.

The v9 unit job installs tests_v9/requirements-test.txt before collecting tests_v9.
This guard prevents the class of failure where a test imports a third-party module
that is absent from the unit-test environment. It also keeps test requirements exact-
pinned and records an auditable generated inventory.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests_v9"
REQ = TESTS / "requirements-test.txt"
JSON_OUT = ROOT / "test_dependency_inventory.generated.json"
CSV_OUT = ROOT / "test_dependency_inventory.csv"

EXACT_PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^=].+$")
BAD_PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?\s*(?:>=|<=|~=|>|<|!=|===)")

# Static third-party imports that are expected to be available when collecting tests_v9.
# Optional imports that are guarded by pytest.importorskip (for example pyarrow/rasterio/
# shapely/pyshp) are deliberately omitted so they can remain optional feature tests.
IMPORT_TO_PACKAGE = {
    "anyio": "anyio",
    "asyncpg": "asyncpg",
    "bcrypt": "bcrypt",
    "cryptography": "cryptography",
    "fastapi": "fastapi",
    "httpx": "httpx",
    "hypothesis": "hypothesis",
    "jose": "python-jose",
    "jwt": "pyjwt",
    "nats": "nats-py",
    "numpy": "numpy",
    "prometheus_client": "prometheus-client",
    "pydantic": "pydantic",
    "pyotp": "pyotp",
    "pytest": "pytest",
    "redis": "redis",
    "respx": "respx",
    "sqlparse": "sqlparse",
    "yaml": "pyyaml",
}

@dataclass(frozen=True)
class TestDependencyRow:
    file: str
    line: int
    requirement: str
    package: str
    exact_pinned: bool
    issue: str


def meaningful(raw: str) -> str:
    return raw.split("#", 1)[0].strip()


def package_name(req: str) -> str:
    base = re.split(r"===|==|>=|<=|~=|!=|>|<", req, maxsplit=1)[0].strip()
    return base.split("[", 1)[0].strip().lower().replace("_", "-")


def classify(req: str) -> tuple[bool, str]:
    if EXACT_PIN_RE.match(req):
        return True, ""
    if BAD_PIN_RE.match(req):
        return False, "range_or_non_exact_pin"
    return False, "unpinned_or_nonstandard_test_requirement"


def dependency_rows() -> list[TestDependencyRow]:
    rows: list[TestDependencyRow] = []
    for line_no, raw in enumerate(REQ.read_text(encoding="utf-8").splitlines(), 1):
        req = meaningful(raw)
        if not req or req.startswith("-") or req.startswith("--"):
            continue
        exact, issue = classify(req)
        rows.append(TestDependencyRow(
            file=str(REQ.relative_to(ROOT)),
            line=line_no,
            requirement=req,
            package=package_name(req),
            exact_pinned=exact,
            issue=issue,
        ))
    return rows


def declared_packages(rows: list[TestDependencyRow]) -> set[str]:
    return {r.package for r in rows}


def imported_modules() -> set[str]:
    imports: set[str] = set()
    for path in sorted(TESTS.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise SystemExit(f"cannot parse {path.relative_to(ROOT)}: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
    return imports


def write_inventory(rows: list[TestDependencyRow]) -> None:
    payload = [asdict(r) for r in rows]
    JSON_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with CSV_OUT.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["file", "line", "requirement", "package", "exact_pinned", "issue"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(payload)


def validate(rows: list[TestDependencyRow]) -> list[str]:
    errors: list[str] = []
    unpinned = [r for r in rows if not r.exact_pinned]
    for r in unpinned:
        errors.append(f"{r.file}:{r.line}: {r.requirement} [{r.issue}]")
    declared = declared_packages(rows)
    imports = imported_modules()
    for module, package in sorted(IMPORT_TO_PACKAGE.items()):
        if module in imports and package not in declared:
            errors.append(
                f"tests_v9 imports '{module}' but '{package}' is missing from tests_v9/requirements-test.txt"
            )
    return errors


def check() -> None:
    before_json = JSON_OUT.read_text(encoding="utf-8") if JSON_OUT.exists() else None
    before_csv = CSV_OUT.read_text(encoding="utf-8") if CSV_OUT.exists() else None
    rows = dependency_rows(); write_inventory(rows)
    drift = []
    if before_json != JSON_OUT.read_text(encoding="utf-8"):
        drift.append(str(JSON_OUT.relative_to(ROOT)))
    if before_csv != CSV_OUT.read_text(encoding="utf-8"):
        drift.append(str(CSV_OUT.relative_to(ROOT)))
    errors = validate(rows)
    if drift:
        raise SystemExit("test dependency inventory drift detected: " + ", ".join(drift))
    if errors:
        raise SystemExit("test dependency contract violations:\n" + "\n".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rows = dependency_rows(); write_inventory(rows)
    errors = validate(rows)
    if args.check:
        # Re-run through drift-aware path after writing once in normal mode.
        check()
        print("test_dependency_inventory_check_ok")
        return
    if errors:
        raise SystemExit("test dependency contract violations:\n" + "\n".join(errors))
    print(f"generated test dependency inventory: {len(rows)} exact-pinned direct test deps")


if __name__ == "__main__":
    main()

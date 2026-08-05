#!/usr/bin/env python3
"""One validator for every ``*.schema.json`` in the repository.

``JSON-SCHEMAS-WITH-NO-VALIDATOR-01``. Measured 2026-08-05: fifteen files named
``*.schema.json`` on this tree, and **nothing validated any of them** — ``jsonschema``
was not installed, not declared a dependency, and imported by no line in the repository.
Eleven of the fifteen declared no ``$schema`` at all, so it was not merely unchecked
which specification they satisfied; it was unstated.

That is worse than an absent contract. A file named ``.schema.json`` is read as a formal
specification, and a reader assumes something enforces it. Nothing did.

**One validator, not four.** The four domains that own schemas (remote_sensing · soil ·
capabilities · food_grain) get no validator of their own: per-domain checkers drift apart
exactly like the two capability-impact engines did in this same repository, where one
reported 0 affected capabilities and the other 12 on the same input.

**The inventory is derived, never listed.** ``git ls-files '*.schema.json'`` is the source
of truth. A policy file declares only what *kind* of schema is acceptable — allowed
drafts, the ``$ref`` rule, the network rule, and dated exceptions. It holds no file list,
because an index that must be edited when a schema is added is the drift this gate closes.

Checks, each of which fails closed:

1. the file parses as JSON;
2. it declares ``$schema``;
3. that meta-schema is one the policy allows *and* the pinned library supports offline;
4. the document is a valid schema under the draft it declares;
5. every ``$ref`` resolves — and is local, never a URL or a sibling file;
6. no resolution touches the network.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "docs/architecture/schema_validation_policy.json"


class SchemaFinding:
    """One reason one file failed, kept as data so the report can be sorted and counted."""

    def __init__(self, path: str, code: str, detail: str) -> None:
        self.path = path
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        return f"  ✗ {self.path}\n      [{self.code}] {self.detail}"


def discover(root: Path = ROOT) -> list[str]:
    """Every tracked ``*.schema.json``. Derived from git, so a new schema is seen at once."""
    out = subprocess.run(
        ["git", "ls-files", "*.schema.json"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return sorted(line for line in out.stdout.splitlines() if line.strip())


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator_for(meta: str):
    """Return the validator class for a meta-schema URI, or None if unsupported.

    Resolved through the library's own registry rather than a hand-written mapping: a
    second mapping is a second thing to keep in step with the library.
    """
    from jsonschema.validators import validator_for

    try:
        cls = validator_for({"$schema": meta}, default=None)
    except Exception:  # noqa: BLE001 - any lookup failure means unsupported
        return None
    return cls


def _iter_refs(node: Any):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _iter_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_refs(value)


def _resolve_local(document: dict[str, Any], pointer: str) -> bool:
    """Resolve a JSON pointer inside this document. No file or network access, by design."""
    if pointer == "#":
        return True
    if not pointer.startswith("#/"):
        return False
    node: Any = document
    for raw in pointer[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if token not in node:
                return False
            node = node[token]
        elif isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                return False
            node = node[int(token)]
        else:
            return False
    return True


def check_file(path: str, policy: dict[str, Any], root: Path = ROOT) -> list[SchemaFinding]:
    findings: list[SchemaFinding] = []
    text = (root / path).read_text(encoding="utf-8")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return [SchemaFinding(path, "INVALID_JSON", f"{exc.msg} (line {exc.lineno})")]

    if not isinstance(document, dict):
        return [SchemaFinding(path, "NOT_AN_OBJECT", f"top level is {type(document).__name__}")]

    meta = document.get("$schema")
    if not meta:
        findings.append(
            SchemaFinding(
                path,
                "NO_META_SCHEMA",
                "declares no $schema — nobody can say which specification reads this file",
            )
        )
    elif meta not in policy["allowed_meta_schemas"]:
        findings.append(
            SchemaFinding(
                path,
                "UNKNOWN_META_SCHEMA",
                f"{meta!r} is not in the policy's allowed set "
                f"({', '.join(sorted(policy['allowed_meta_schemas']))})",
            )
        )
    else:
        validator_cls = _validator_for(meta)
        if validator_cls is None:
            findings.append(
                SchemaFinding(
                    path, "UNSUPPORTED_BY_LIBRARY", f"the pinned jsonschema cannot handle {meta!r}"
                )
            )
        else:
            try:
                validator_cls.check_schema(document)
            except Exception as exc:  # noqa: BLE001 - the library raises several types
                findings.append(
                    SchemaFinding(path, "INVALID_SCHEMA", f"{type(exc).__name__}: {exc}")
                )

    for ref in _iter_refs(document):
        if policy["ref_policy"]["local_only"] and not ref.startswith("#"):
            findings.append(
                SchemaFinding(
                    path,
                    "EXTERNAL_REF",
                    f"{ref!r} — external references make a green result describe the "
                    "environment, not the contract",
                )
            )
        elif ref.startswith("#") and not _resolve_local(document, ref):
            findings.append(SchemaFinding(path, "UNRESOLVED_REF", f"{ref!r} points at nothing"))

    return findings


def _expired_exceptions(policy: dict[str, Any], today: date) -> list[str]:
    """An exception without a live expiry is a permanent decision nobody owns."""
    problems = []
    for entry in policy.get("exceptions", []):
        missing = sorted(
            {"path", "reason", "owner", "decision_id", "expires_on"} - set(entry or {})
        )
        if missing:
            problems.append(f"exception missing {missing}: {entry}")
            continue
        if date.fromisoformat(entry["expires_on"]) < today:
            problems.append(
                f"exception expired {entry['expires_on']} for {entry['path']} "
                f"(owner {entry['owner']}, {entry['decision_id']})"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate every tracked *.schema.json (the default; the flag makes intent explicit)",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print(
            "✗ jsonschema is not installed — declared in tests_v9/requirements-test.txt.\n"
            "  A validator without its library is a gate that never fires; this fails\n"
            "  closed rather than skipping quietly.",
            file=sys.stderr,
        )
        return 2

    policy = load_policy()
    files = discover()
    exempt = {entry["path"] for entry in policy.get("exceptions", []) if "path" in entry}

    findings: list[SchemaFinding] = []
    for path in files:
        if path in exempt:
            continue
        findings.extend(check_file(path, policy))

    expired = _expired_exceptions(policy, date.today())

    if args.json:
        print(
            json.dumps(
                {
                    "discovered": len(files),
                    "exempt": sorted(exempt),
                    "findings": [
                        {"path": f.path, "code": f.code, "detail": f.detail} for f in findings
                    ],
                    "expired_exceptions": expired,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"schema_validation_guard: {len(files)} مخطَّطاً مُكتشَفاً من git")
        for problem in expired:
            print(f"  ✗ {problem}")
        for finding in findings:
            print(finding)
        if not findings and not expired:
            drafts = sorted(
                {json.loads((ROOT / p).read_text(encoding="utf-8"))["$schema"] for p in files}
            )
            print(f"  ✓ الكلّ صالح · ميتا-مخطَّطات مستعمَلة: {len(drafts)} · مراجع خارجيّة: 0 · شبكة: 0")
            print("schema_validation_guard_ok")

    return 1 if (findings or expired) else 0


if __name__ == "__main__":
    raise SystemExit(main())

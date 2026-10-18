#!/usr/bin/env python3
"""Read-only re-measurement for OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01.

Imports ``scripts/ci/db_writer_ownership_guard.py`` as the measuring engine (no second
scanner, no second write regex) and adds only what the guard does not print:

* ``file:line`` for every undeclared write (the guard records files, not lines);
* signals per write that feed a NON-BINDING hint ("contract likely stale" /
  "code likely wrong" / "cannot tell"). The verdict per write belongs to the owner.

Nothing is written into the tree. Output: JSON on stdout.

    python3 certification/evidence/architecture_remeasure_20261017/measure_ownership.py
"""

from __future__ import annotations

import ast
import glob
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
GUARD_PATH = ROOT / "scripts" / "ci" / "db_writer_ownership_guard.py"
EXTRACTION_MAP = ROOT / "docs" / "architecture" / "platform_extraction_map.json"


def _load_guard():
    spec = importlib.util.spec_from_file_location("db_writer_ownership_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def _owner_dirs(owner: str) -> list[str]:
    mapped = [d for d, ident in guard._DIRECTORY_IDENTITY.items() if ident == owner]
    return mapped or [owner]


def write_lines(rel: str, table: str) -> list[int]:
    """Lines of SQL write statements on ``table`` inside string literals of ``rel``.

    Same literals and same ``_WRITE`` regex as the guard; the line is the first source
    line inside the literal's span that names the table (falls back to the literal start).
    """
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    src_lines = text.splitlines()
    tree = ast.parse(text)
    word = re.compile(rf"\b{re.escape(table)}\b", re.IGNORECASE)
    out: set[int] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if len(node.value) < guard._MIN_SQL_LEN:
            continue
        hit = any(
            guard._matched_table(m).lower() == table for m in guard._WRITE.finditer(node.value)
        )
        if not hit:
            continue
        start, end = node.lineno, node.end_lineno or node.lineno
        line = next(
            (n for n in range(start, end + 1) if word.search(src_lines[n - 1])),
            start,
        )
        out.add(line)
    return sorted(out)


def compose_builds() -> dict[str, list[str]]:
    """{services/<dir>: [compose file::service]} from build contexts / dockerfiles."""
    out: dict[str, list[str]] = {}
    for f in sorted(glob.glob(str(ROOT / "docker-compose*.yml"))):
        try:
            doc = yaml.safe_load(Path(f).read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for name, svc in (doc.get("services") or {}).items():
            if not isinstance(svc, dict):
                continue
            build = svc.get("build")
            parts = []
            if isinstance(build, dict):
                parts = [str(build.get("context") or ""), str(build.get("dockerfile") or "")]
            elif isinstance(build, str):
                parts = [build]
            blob = " ".join(parts)
            for m in re.finditer(r"services/([A-Za-z0-9_.-]+)", blob):
                out.setdefault(m.group(1), []).append(f"{Path(f).name}::{name}")
    return {k: sorted(set(v)) for k, v in out.items()}


def owner_mentions(owner: str, table: str) -> list[str]:
    """Files under the owner's service dir naming the table at all (reads, DDL, ORM, docs)."""
    hits: list[str] = []
    for d in _owner_dirs(owner):
        base = ROOT / "services" / d
        if not base.is_dir():
            continue
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "grep", "-l", "-w", "-i", table, "--", f"services/{d}"],
            capture_output=True,
            text=True,
            check=False,
        )
        hits.extend(line for line in proc.stdout.splitlines() if line)
    return sorted(hits)


def migration_sources(table: str) -> list[str]:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "grep",
            "-l",
            "-i",
            "-E",
            rf"CREATE TABLE (IF NOT EXISTS )?([a-z_]+\.)?{table}\b",
            "--",
            "migrations",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted(line for line in proc.stdout.splitlines() if line)


M03_CARD = "docs/architecture/m03_command_path_adjudication.md"
M03_TABLES = {"actuator_command_outbox", "iot_command_dispatch"}


def hint(row: dict) -> tuple[str, list[str]]:
    """Non-binding hint from declared rules over measured signals. Not a verdict.

    Rules, in order (first match wins):
      R1 dual-writer (owner also writes)                  -> code likely wrong
      R2 writer is scripts/ (tooling)                     -> cannot tell
      R3 owner is sahool-platform, writer is another
         service, sahool-platform never writes the table  -> contract likely stale
      R4 writer is sahool-platform, owner is a live
         extraction target in platform_extraction_map     -> code likely wrong (pre-extraction)
      R5 anything else (service -> non-platform service)  -> cannot tell
    """
    why: list[str] = []
    owner = row["declared_owner"]
    writer = row["writer"]
    if row["table"] in M03_TABLES:
        why.append(f"M-03 table: options and recommendation are in {M03_CARD} (owner decision)")
    if row["category"] == "dual-writer":
        why.append(
            f"R1: owner {owner} has a measured SQL write site for this table AND {writer} "
            "writes it too; two writers is a code-side conflict whatever the contract says"
        )
        return "code likely wrong", why
    if writer == "scripts":
        why.append(
            f"R2: writer is tooling ({row['files'][0]}), not a service; the contract models "
            "services only, so it neither authorises nor forbids ops/e2e writes"
        )
        return "cannot tell", why
    if owner == "sahool-platform" and writer != "sahool-platform" and not row["owner_writes_table"]:
        why.append(
            f"R3: the only measured writer is {writer}; sahool-platform (declared owner, the "
            "monolith being decomposed) has no SQL write site for it, so the write already sits "
            "outside the monolith and the contract still names the monolith"
        )
        if row["owner_mentions_table"]:
            why.append(
                f"sahool-platform still names the table in {len(row['owner_mentions_table'])} "
                "file(s) (reads/DDL/docs) - check none is an ORM write before re-declaring"
            )
        return "contract likely stale", why
    if writer == "sahool-platform" and row["owner_is_live_extraction_target"]:
        why.append(
            f"R4: owner {owner} is a live target_owner in platform_extraction_map.json "
            f"({row['owner_extraction_route_count']} routes) and is built in "
            f"{len(row['owner_compose_builds'])} compose service(s); the contract encodes the "
            "extraction end-state and the write is still in the monolith; re-declaring is "
            "blocked by ownership_extraction_alignment_guard while the target is live"
        )
        if not row["owner_mentions_table"]:
            why.append(f"{owner} does not name this table anywhere in services/ yet")
        return "code likely wrong", why
    why.append(
        f"R5: service-to-service ({writer} writes, {owner} declared owner); "
        f"{owner} names the table in {len(row['owner_mentions_table'])} file(s) and has "
        "no SQL-literal write site; the scanner cannot see ORM/.sql writes"
    )
    return "cannot tell", why


def contract_names_not_in_tree(contract: dict) -> list[dict]:
    """Every owner/writer/reader/mirror name in the contract with no directory behind it."""
    roots = set(guard._SERVICE_ROOTS) | {"*"}
    seen: dict[tuple[str, str], int] = {}
    for meta in contract.values():
        if not isinstance(meta, dict):
            continue
        for field in ("owner", "mirror"):
            if meta.get(field):
                seen[(field, meta[field])] = seen.get((field, meta[field]), 0) + 1
        for field in ("writers", "readers"):
            for name in meta.get(field) or []:
                seen[(field, name)] = seen.get((field, name), 0) + 1
    missing = []
    for (field, name), count in sorted(seen.items()):
        if name in roots or any((ROOT / "services" / d).is_dir() for d in _owner_dirs(name)):
            continue
        missing.append({"field": field, "name": name, "tables": count})
    return missing


def main() -> int:
    contract = guard.load_contract()
    sites = guard.write_sites()
    violations = guard.survey()
    baseline = guard._baseline()
    rows = guard.triage_rows(contract=contract, sites=sites, violations=violations)
    builds = compose_builds()
    routes = json.loads(EXTRACTION_MAP.read_text(encoding="utf-8")).get("routes") or []
    targets: dict[str, int] = {}
    for r in routes:
        if isinstance(r, dict) and r.get("target_owner"):
            targets[r["target_owner"]] = targets.get(r["target_owner"], 0) + 1
    out_rows = []
    for key, row in sorted(rows.items()):
        table, owner = row["table"], row["declared_owner"]
        owner_builds = [b for d in _owner_dirs(owner or "") for b in builds.get(d, [])]
        enriched = {
            "key": key,
            "table": table,
            "writer": row["writer"],
            "declared_owner": owner,
            "declared_writers": row["declared_writers"],
            "declared_readers": (contract.get(table) or {}).get("readers"),
            "sites": [
                f"{f}:{line}" for f in row["files"] for line in (write_lines(f, table) or [0])
            ],
            "files": row["files"],
            "category": row["category"],
            "owner_writes_table": row["owner_writes_table"],
            "measured_writers_of_table": row["measured_writers_of_table"],
            "owner_mentions_table": owner_mentions(owner or "", table),
            "owner_built_in_any_compose": bool(owner_builds),
            "owner_compose_builds": owner_builds,
            "owner_is_live_extraction_target": owner in targets,
            "owner_extraction_route_count": targets.get(owner, 0),
            "table_created_in_migrations": migration_sources(table),
        }
        h, why = hint(enriched)
        enriched["hint"] = h
        enriched["hint_evidence"] = why
        enriched["hint_is_binding"] = False
        out_rows.append(enriched)
    by_service: dict[str, int] = {}
    by_hint: dict[str, int] = {}
    for r in out_rows:
        by_service[r["writer"]] = by_service.get(r["writer"], 0) + 1
        by_hint[r["hint"]] = by_hint.get(r["hint"], 0) + 1
    doc = {
        "engine": "scripts/ci/db_writer_ownership_guard.py (imported, unmodified)",
        "contract_table_count": len(contract),
        "baseline_file_count": len(baseline),
        "measured_violation_count": len(violations),
        "baseline_equals_measurement": sorted(baseline) == sorted(violations),
        "by_writer_service": dict(sorted(by_service.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_hint": by_hint,
        "contract_service_names_not_in_tree": contract_names_not_in_tree(contract),
        "excluded_sqlite_only": guard.excluded_write_sites(contract=contract),
        "rows": out_rows,
    }
    json.dump(doc, sys.stdout, ensure_ascii=False, indent=1, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

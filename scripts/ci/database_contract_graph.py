#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migrations"
OUT = ROOT / "database-audit" / "generated"
SKIP = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "generated",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
CREATE_RE = re.compile(
    r'CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?:public|core)\.)?"?([a-zA-Z_][\w$]*)"?',
    re.I,
)
TENANT_RE = re.compile(r"\btenant_id\b", re.I)
ENABLE_RE = re.compile(
    r'ALTER\s+TABLE\s+(?:ONLY\s+)?(?:(?:public|core)\.)?"?([\w$]+)"?\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY',
    re.I,
)
FORCE_RE = re.compile(
    r'ALTER\s+TABLE\s+(?:ONLY\s+)?(?:(?:public|core)\.)?"?([\w$]+)"?\s+FORCE\s+ROW\s+LEVEL\s+SECURITY',
    re.I,
)
POLICY_RE = re.compile(
    r'CREATE\s+POLICY\s+"?([\w$]+)"?\s+ON\s+(?:(?:public|core)\.)?"?([\w$]+)"?(.*?)(?=;)',
    re.I | re.S,
)
TABLE_REF_RE = re.compile(
    r'\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+(?:(?:public|core)\.)?"?([a-zA-Z_][\w$]*)"?', re.I
)


def walk_files(roots, suffixes):
    for root in roots:
        if not root.exists():
            continue
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP]
            for fn in fns:
                p = Path(dp) / fn
                if p.suffix.lower() in suffixes:
                    yield p


def manifest_entries():
    p = MIG / "MANIFEST.txt"
    entries = []
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            entries.append(s)
    return entries


def scan():
    entries = manifest_entries()
    pos = {n: i for i, n in enumerate(entries)}
    sql_files = sorted(MIG.glob("*.sql"))
    manifest_missing = [n for n in entries if not (MIG / n).exists()]
    unlisted = [p.name for p in sql_files if p.name not in pos and not p.name.endswith(".down.sql")]
    tables = {}
    enables = set()
    forces = set()
    policies = []
    for p in sql_files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in CREATE_RE.finditer(text):
            t = m.group(1).lower()
            segment = text[
                m.start() : text.find(";", m.start()) + 1
                if text.find(";", m.start()) != -1
                else m.start() + 4000
            ]
            tables.setdefault(
                t,
                {
                    "table": t,
                    "created_in": p.name,
                    "manifest_position": pos.get(p.name),
                    "has_tenant_id": bool(TENANT_RE.search(segment)),
                    "code_readers": set(),
                    "code_writers": set(),
                },
            )
        enables |= {x.lower() for x in ENABLE_RE.findall(text)}
        forces |= {x.lower() for x in FORCE_RE.findall(text)}
        for m in POLICY_RE.finditer(text):
            body = m.group(3)
            policies.append(
                {
                    "name": m.group(1),
                    "table": m.group(2).lower(),
                    "has_using": bool(re.search(r"\bUSING\s*\(", body, re.I)),
                    "has_with_check": bool(re.search(r"\bWITH\s+CHECK\s*\(", body, re.I)),
                    "source": p.name,
                }
            )
    roots = [ROOT / "services", ROOT / "shared", ROOT / "sahool-platform"]
    for p in walk_files(roots, {".py", ".sql", ".ts", ".tsx", ".js"}):
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel = str(p.relative_to(ROOT))
        for t in set(x.lower() for x in TABLE_REF_RE.findall(text)):
            if t not in tables:
                continue
            if re.search(
                rf'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:(?:public|core)\.)?"?{re.escape(t)}"?',
                text,
                re.I,
            ):
                tables[t]["code_writers"].add(rel)
            if re.search(
                rf'\b(?:FROM|JOIN)\s+(?:(?:public|core)\.)?"?{re.escape(t)}"?', text, re.I
            ):
                tables[t]["code_readers"].add(rel)
    policy_by = {}
    for p in policies:
        policy_by.setdefault(p["table"], []).append(p)
    rows = []
    for t, d in sorted(tables.items()):
        ps = policy_by.get(t, [])
        tenant = d["has_tenant_id"]
        rows.append(
            {
                **d,
                "code_readers": sorted(d["code_readers"]),
                "code_writers": sorted(d["code_writers"]),
                "rls_enabled": t in enables,
                "rls_forced": t in forces,
                "policy_count": len(ps),
                "write_policy_with_check": any(x["has_with_check"] for x in ps),
                "tenant_rls_gap": bool(tenant and (t not in enables or t not in forces)),
            }
        )
    summary = {
        "manifest_entries": len(entries),
        "sql_files": len(sql_files),
        "manifest_missing_count": len(manifest_missing),
        "unlisted_sql_count": len(unlisted),
        "tables": len(rows),
        "tenant_tables": sum(r["has_tenant_id"] for r in rows),
        "rls_enabled": sum(r["rls_enabled"] for r in rows),
        "rls_forced": sum(r["rls_forced"] for r in rows),
        "tenant_rls_gaps": sum(r["tenant_rls_gap"] for r in rows),
        "policies": len(policies),
        "runtime_verified": False,
        "production_certified": False,
    }
    return {
        "schema_version": 1,
        "summary": summary,
        "manifest": {"entries": entries, "missing": manifest_missing, "unlisted_sql": unlisted},
        "tables": rows,
        "policies": sorted(policies, key=lambda x: (x["table"], x["name"], x["source"])),
    }


def render(data):
    OUT.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (OUT / "database_contract_graph.json").write_text(payload, encoding="utf-8")
    (OUT / "database_contract_summary.json").write_text(
        json.dumps(data["summary"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (OUT / "database_tables.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "table",
            "created_in",
            "manifest_position",
            "has_tenant_id",
            "rls_enabled",
            "rls_forced",
            "policy_count",
            "write_policy_with_check",
            "tenant_rls_gap",
            "code_reader_count",
            "code_writer_count",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in data["tables"]:
            x = {k: r.get(k) for k in fields}
            x["code_reader_count"] = len(r["code_readers"])
            x["code_writer_count"] = len(r["code_writers"])
            w.writerow(x)
    s = data["summary"]
    gaps = [r for r in data["tables"] if r["tenant_rls_gap"]]
    md = (
        [
            "# Database Contract Graph",
            "",
            "> Static repository evidence only; PostgreSQL was not started.",
            "",
            "## Summary",
            "",
        ]
        + [f"- **{k}**: {v}" for k, v in s.items()]
        + ["", "## Tenant RLS review candidates", ""]
    )
    md += [
        f"- `{r['table']}` — enabled={r['rls_enabled']}, forced={r['rls_forced']}, policies={r['policy_count']}"
        for r in gaps
    ] or ["- None detected by the static parser."]
    (OUT / "DATABASE_CONTRACT_REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    data = scan()
    expected = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target = OUT / "database_contract_graph.json"
    if a.generate:
        render(data)
        print(json.dumps(data["summary"], indent=2))
        return
    if a.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            print("database contract drift: run --generate", file=sys.stderr)
            raise SystemExit(1)
        print("database contract graph: PASS")
        return
    ap.error("choose --generate or --check")


if __name__ == "__main__":
    main()

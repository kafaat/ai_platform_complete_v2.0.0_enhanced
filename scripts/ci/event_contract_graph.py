#!/usr/bin/env python3
"""Generate a conservative static NATS/JetStream event contract graph.

Only literal subjects passed directly to publish/subscribe calls are treated as
resolved contracts. Dynamic subjects are inventoried separately and never
classified as missing producers/consumers.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import os
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "event-audit" / "generated"
JSON_OUT = OUT / "event_contract_graph.json"
SUMMARY_OUT = OUT / "event_contract_summary.json"
REPORT_OUT = OUT / "EVENT_CONTRACT_REPORT.md"
CSV_OUT = OUT / "event_contracts.csv"
SCAN_ROOTS = ("services", "shared", "sahool-platform")
SKIP = {
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "generated",
    "__pycache__",
    ".git",
    ".pytest_cache",
}

PUBLISH_NAMES = {"publish"}
SUBSCRIBE_NAMES = {"subscribe"}


@dataclass(frozen=True)
class Contract:
    kind: str
    subject: str | None
    file: str
    line: int
    component: str
    client_expr: str
    durable: str | None = None
    queue: str | None = None
    dynamic_expr: str | None = None


def py_files() -> Iterable[Path]:
    for root_name in SCAN_ROOTS:
        base = ROOT / root_name
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP)
            for name in sorted(filenames):
                if name.endswith(".py") and not name.startswith("test_"):
                    yield Path(dirpath) / name


def component_for(path: Path) -> str:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if parts[0] == "services" and len(parts) > 1:
        name = parts[1]
        return "erp-bridge" if name == "odoo-bridge" else name
    if parts[0] == "sahool-platform":
        return "sahool-platform"
    return "shared"


def literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def expr_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return node.__class__.__name__


def keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def parse_file(path: Path) -> list[Contract]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return []
    rel = path.relative_to(ROOT).as_posix()
    comp = component_for(path)
    rows: list[Contract] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        if method not in PUBLISH_NAMES | SUBSCRIBE_NAMES:
            continue
        # Avoid obvious non-message-bus APIs.
        client = expr_text(node.func.value)
        client_low = client.lower()
        if any(x in client_low for x in ("redis", "pubsub", "mqtt")):
            continue
        subject_node = node.args[0] if node.args else keyword(node, "subject")
        if subject_node is None:
            continue
        subj = literal(subject_node)
        kind = "producer" if method in PUBLISH_NAMES else "consumer"
        durable = literal(keyword(node, "durable"))
        queue = literal(keyword(node, "queue"))
        rows.append(
            Contract(
                kind=kind,
                subject=subj,
                file=rel,
                line=getattr(node, "lineno", 0),
                component=comp,
                client_expr=client,
                durable=durable,
                queue=queue,
                dynamic_expr=None if subj is not None else expr_text(subject_node),
            )
        )
    return rows


def build() -> dict:
    contracts = sorted(
        (c for p in py_files() for c in parse_file(p)),
        key=lambda c: (c.subject or "~", c.kind, c.file, c.line),
    )
    by_subject: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: {"producers": [], "consumers": []}
    )
    dynamic = []
    for c in contracts:
        data = asdict(c)
        if c.subject is None:
            dynamic.append(data)
        else:
            by_subject[c.subject]["producers" if c.kind == "producer" else "consumers"].append(data)
    subjects = []
    producer_only = []
    consumer_only = []
    for subject in sorted(by_subject):
        item = {"subject": subject, **by_subject[subject]}
        item["status"] = (
            "matched"
            if item["producers"] and item["consumers"]
            else ("producer_only" if item["producers"] else "consumer_only")
        )
        subjects.append(item)
        if item["status"] == "producer_only":
            producer_only.append(subject)
        elif item["status"] == "consumer_only":
            consumer_only.append(subject)
    duplicate_durables = []
    durable_map = defaultdict(list)
    for c in contracts:
        if c.kind == "consumer" and c.durable:
            durable_map[(c.subject, c.durable)].append(asdict(c))
    for (subject, durable), refs in sorted(durable_map.items(), key=lambda x: str(x[0])):
        components = sorted({r["component"] for r in refs})
        if len(components) > 1:
            duplicate_durables.append(
                {
                    "subject": subject,
                    "durable": durable,
                    "components": components,
                    "references": refs,
                }
            )
    summary = {
        "files_scanned": sum(1 for _ in py_files()),
        "resolved_contracts": sum(1 for c in contracts if c.subject is not None),
        "dynamic_contracts": len(dynamic),
        "subjects": len(subjects),
        "matched_subjects": sum(s["status"] == "matched" for s in subjects),
        "producer_only_subjects": len(producer_only),
        "consumer_only_subjects": len(consumer_only),
        "cross_component_duplicate_durables": len(duplicate_durables),
        "runtime_verified": False,
        "production_certified": False,
    }
    return {
        "schema_version": 1,
        "scope": "static_literal_nats_jetstream_contracts",
        "limitations": [
            "Dynamic subjects are review-only and excluded from missing producer/consumer findings.",
            "Static presence does not prove stream provisioning, delivery, acknowledgement, or runtime reachability.",
            "Producer-only and consumer-only subjects may be intentional external boundaries.",
        ],
        "summary": summary,
        "subjects": subjects,
        "dynamic_contracts": dynamic,
        "review": {
            "producer_only_subjects": producer_only,
            "consumer_only_subjects": consumer_only,
            "cross_component_duplicate_durables": duplicate_durables,
        },
    }


def canonical(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write(data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(canonical(data), encoding="utf-8")
    SUMMARY_OUT.write_text(canonical(data["summary"]), encoding="utf-8")
    with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "subject",
                "status",
                "producer_count",
                "consumer_count",
                "producer_components",
                "consumer_components",
            ]
        )
        for s in data["subjects"]:
            w.writerow(
                [
                    s["subject"],
                    s["status"],
                    len(s["producers"]),
                    len(s["consumers"]),
                    ";".join(sorted({x["component"] for x in s["producers"]})),
                    ";".join(sorted({x["component"] for x in s["consumers"]})),
                ]
            )
    sm = data["summary"]
    report = f"""# SAHOOL Static Event/NATS Contract Report

## Scope

Conservative static inventory of literal NATS/JetStream subjects. Dynamic subjects are listed but are not used to declare missing producers or consumers.

## Summary

| Metric | Value |
|---|---:|
| Python files scanned | {sm["files_scanned"]} |
| Resolved literal contracts | {sm["resolved_contracts"]} |
| Dynamic contracts | {sm["dynamic_contracts"]} |
| Unique literal subjects | {sm["subjects"]} |
| Matched subjects | {sm["matched_subjects"]} |
| Producer-only subjects | {sm["producer_only_subjects"]} |
| Consumer-only subjects | {sm["consumer_only_subjects"]} |
| Cross-component duplicate durables | {sm["cross_component_duplicate_durables"]} |
| Runtime verified | No |
| Production certified | No |

## Review boundary

Producer-only and consumer-only entries are review candidates, not automatic defects. They can represent external integrations, future consumers, generic publishers, or dynamic subject construction.
"""
    REPORT_OUT.write_text(report, encoding="utf-8")


def check(data: dict) -> int:
    expected = canonical(data)
    if not JSON_OUT.exists() or JSON_OUT.read_text(encoding="utf-8") != expected:
        print("event contract graph drift: run --generate")
        return 1
    print("event contract graph: PASS")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--generate", action="store_true")
    g.add_argument("--check", action="store_true")
    args = p.parse_args()
    data = build()
    if args.generate:
        write(data)
        print(canonical(data["summary"]).strip())
        return 0
    return check(data)


if __name__ == "__main__":
    raise SystemExit(main())

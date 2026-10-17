#!/usr/bin/env python3
"""Generate a conservative static NATS/JetStream event contract graph.

Only literal subjects reaching publish/subscribe calls are treated as resolved
contracts. Dynamic subjects are inventoried separately and never classified as
missing producers/consumers.

A subject passed as a *name* is resolved only in two provable shapes, each tagged
in ``resolution`` so a reader can tell them from a literal argument:

* ``module_constant_loop`` -- ``for subject in SUBJECTS: js.subscribe(subject)``
  where ``SUBJECTS`` is a module-level tuple/list of string literals (one contract
  per literal);
* ``local_token_template`` -- ``subject = f"sahool.tenant.{t}.x.{f}.done"`` assigned
  exactly once in the enclosing function, every placeholder filling a whole
  dot-delimited token; each placeholder becomes the NATS single-token wildcard ``*``
  (the same pattern a subscriber declares).

Why (2026-10-17, WEATHER-FORECAST-TOPIC-HAS-NO-PUBLISHER-01): the only literal
NATS edges this scanner ever saw belonged to ``weather-polygon-worker`` -- a scaffold
subscribed to a subject with no publisher. Removing it left the graph with zero
EMITS/CONSUMES while the platform's real flows (vegetation's satellite event, the
canonical learning worker's subscriptions) stayed invisible behind a variable.
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
    resolution: str = "literal"


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


def _module_literal_sequences(tree: ast.Module) -> dict[str, list[str]]:
    """``NAME = ("a", "b")`` at module level, every element a string literal."""
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Tuple | ast.List)
            and node.value.elts
            and all(literal(e) is not None for e in node.value.elts)
        ):
            out[node.targets[0].id] = [literal(e) for e in node.value.elts]  # type: ignore[misc]
    return out


def _token_template(node: ast.AST) -> str | None:
    """f-string whose every placeholder fills a whole dot-delimited token ⇒ ``*``."""
    if not isinstance(node, ast.JoinedStr):
        return None
    text = ""
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text += value.value
        elif isinstance(value, ast.FormattedValue):
            text += "\0"
        else:
            return None
    tokens = text.split(".")
    if not tokens or tokens[0] != "sahool":
        return None
    out = []
    for token in tokens:
        if "\0" in token and token != "\0":
            return None  # placeholder shares a token with literal text: not a NATS token
        out.append("*" if token == "\0" else token)
    return ".".join(out) if "*" in out else None


def _function_resolutions(
    func: ast.AST, module_seqs: dict[str, list[str]]
) -> dict[str, tuple[list[str], str]]:
    """name ⇒ (subjects, resolution) inside one function, in the two provable shapes."""
    params = {
        a.arg
        for a in [
            *func.args.posonlyargs,  # type: ignore[attr-defined]
            *func.args.args,  # type: ignore[attr-defined]
            *func.args.kwonlyargs,  # type: ignore[attr-defined]
        ]
    }
    assigned: dict[str, list[ast.AST]] = defaultdict(list)
    loops: dict[str, list[ast.AST]] = defaultdict(list)
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned[target.id].append(node.value)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign) and isinstance(node.target, ast.Name):
            assigned[node.target.id].append(node.value or node)
        elif isinstance(node, ast.For | ast.AsyncFor) and isinstance(node.target, ast.Name):
            loops[node.target.id].append(node.iter)
    out: dict[str, tuple[list[str], str]] = {}
    for name, iters in loops.items():
        if name in params or name in assigned or len(iters) != 1:
            continue
        it = iters[0]
        if isinstance(it, ast.Name) and it.id in module_seqs:
            out[name] = (module_seqs[it.id], "module_constant_loop")
    for name, values in assigned.items():
        if name in params or name in loops or len(values) != 1:
            continue
        template = _token_template(values[0])
        if template:
            out[name] = ([template], "local_token_template")
    return out


def _enclosing_functions(tree: ast.Module) -> dict[int, ast.AST]:
    """id(call) ⇒ innermost enclosing function."""
    owner: dict[int, ast.AST] = {}

    def visit(node: ast.AST, func: ast.AST | None) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else func
            if isinstance(child, ast.Call) and inner is not None:
                owner[id(child)] = inner
            visit(child, inner)

    visit(tree, None)
    return owner


def parse_file(path: Path) -> list[Contract]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return []
    rel = path.relative_to(ROOT).as_posix()
    comp = component_for(path)
    module_seqs = _module_literal_sequences(tree)
    owners = _enclosing_functions(tree)
    resolutions: dict[int, dict[str, tuple[list[str], str]]] = {}
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
        kind = "producer" if method in PUBLISH_NAMES else "consumer"
        durable = literal(keyword(node, "durable"))
        queue = literal(keyword(node, "queue"))
        subj = literal(subject_node)
        resolved: tuple[list[str], str] | None = None
        func = owners.get(id(node))
        if subj is None and isinstance(subject_node, ast.Name) and func is not None:
            if id(func) not in resolutions:
                resolutions[id(func)] = _function_resolutions(func, module_seqs)
            resolved = resolutions[id(func)].get(subject_node.id)
        subjects, resolution = resolved or ([subj], "literal")
        for subject in subjects:
            rows.append(
                Contract(
                    kind=kind,
                    subject=subject,
                    file=rel,
                    line=getattr(node, "lineno", 0),
                    component=comp,
                    client_expr=client,
                    durable=durable,
                    queue=queue,
                    dynamic_expr=None if subject is not None else expr_text(subject_node),
                    resolution=resolution if subject is not None else "dynamic",
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
            "A subject passed as a name is resolved only from a loop over a module-level tuple of literals or a single local f-string whose placeholders fill whole tokens (as '*'); see each contract's resolution.",
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

Conservative static inventory of literal NATS/JetStream subjects (a name argument is resolved only from a loop over a module-level tuple of literals, or a single local f-string whose placeholders fill whole tokens, rendered as `*`). Dynamic subjects are listed but are not used to declare missing producers or consumers.

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

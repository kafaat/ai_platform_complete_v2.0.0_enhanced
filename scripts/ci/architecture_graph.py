#!/usr/bin/env python3
"""Build a conservative service architecture graph from repository evidence.

The graph is repository evidence only. It does not claim that an edge is active at runtime.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "architecture" / "generated"
SERVICE_DIRS = [ROOT / "services", ROOT / "apps", ROOT / "sahool-platform"]
SKIP = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
URL_RE = re.compile(
    r"https?://(?:\$\{)?([A-Z][A-Z0-9_]*_(?:URL|HOST)|[a-z0-9][a-z0-9_-]*)(?:\})?", re.I
)
ENV_SERVICE_RE = re.compile(r"\b([A-Z][A-Z0-9_]+)_(?:URL|HOST)\b")


def canonical(name: str) -> str:
    name = name.strip().lower().replace("_", "-")
    aliases = {"odoo-bridge": "erp-bridge", "sahool-platform": "platform"}
    return aliases.get(name, name)


def service_nodes() -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for base in SERVICE_DIRS:
        if not base.exists():
            continue
        if base.name == "sahool-platform":
            candidates = [base]
        else:
            candidates = [p for p in base.iterdir() if p.is_dir() and p.name not in SKIP]
        for p in candidates:
            if (
                any(
                    (p / marker).exists()
                    for marker in (
                        "main.py",
                        "app.py",
                        "package.json",
                        "pyproject.toml",
                        "Dockerfile",
                    )
                )
                or (p / "src").exists()
            ):
                sid = canonical(p.name)
                nodes.setdefault(sid, {"id": sid, "paths": [], "kind": "service"})["paths"].append(
                    str(p.relative_to(ROOT))
                )
    return nodes


def python_edges(nodes: dict[str, dict]) -> list[dict]:
    path_owner: list[tuple[Path, str]] = []
    for sid, node in nodes.items():
        for rel in node["paths"]:
            path_owner.append((ROOT / rel, sid))
    edges = []
    seen = set()
    for base, src in path_owner:
        for py in base.rglob("*.py"):
            if any(part in SKIP for part in py.parts):
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            imports = []
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    imports.extend(a.name for a in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module:
                    imports.append(n.module)
            text = py.read_text(encoding="utf-8", errors="ignore")
            for target, _tnode in nodes.items():
                if target == src:
                    continue
                target_norm = target.replace("-", "_")
                target_base = target_norm.removesuffix("_service")
                matched = False
                for imp in imports:
                    parts = {part.lower().replace("-", "_") for part in imp.split(".")}
                    if target_norm in parts or (target_base and target_base in parts):
                        matched = True
                        break
                env_match = any(
                    m.group(1).lower().removesuffix("_service") == target_base
                    for m in ENV_SERVICE_RE.finditer(text)
                )
                if matched or env_match:
                    evidence = str(py.relative_to(ROOT))
                    key = (src, target, "code-reference", evidence)
                    if key not in seen:
                        seen.add(key)
                        edges.append(
                            {
                                "source": src,
                                "target": target,
                                "kind": "code-reference",
                                "evidence": evidence,
                            }
                        )
    return edges


def compose_edges(nodes: dict[str, dict]) -> list[dict]:
    edges = []
    seen = set()
    for f in list(ROOT.glob("docker-compose*.yml")) + list(ROOT.glob("docker-compose*.yaml")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        in_services = False
        current = None
        in_depends = False
        service_indent = None
        for line in lines:
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if stripped == "services:":
                in_services = True
                continue
            if not in_services:
                continue
            m = re.match(r"^\s{2}([A-Za-z0-9_.-]+):\s*(?:#.*)?$", line)
            if m:
                current = canonical(m.group(1))
                service_indent = indent
                in_depends = False
                continue
            if current and stripped.startswith("depends_on:"):
                in_depends = True
                continue
            if in_depends:
                m1 = re.match(r"^\s*-\s*([A-Za-z0-9_.-]+)\s*$", line)
                m2 = re.match(r"^\s+([A-Za-z0-9_.-]+):(?:\s|$)", line)
                dep = canonical((m1 or m2).group(1)) if (m1 or m2) else None
                if dep:
                    nodes.setdefault(
                        current, {"id": current, "paths": [], "kind": "compose-service"}
                    )
                    nodes.setdefault(dep, {"id": dep, "paths": [], "kind": "compose-service"})
                    key = (current, dep, str(f.relative_to(ROOT)))
                    if key not in seen:
                        seen.add(key)
                        edges.append(
                            {
                                "source": current,
                                "target": dep,
                                "kind": "compose-depends-on",
                                "evidence": key[2],
                            }
                        )
                elif stripped and indent <= (service_indent or 2) + 2:
                    in_depends = False
    return edges


def scc(nodes: list[str], edges: list[dict]) -> list[list[str]]:
    graph = defaultdict(list)
    for e in edges:
        graph[e["source"]].append(e["target"])
    index = 0
    stack = []
    on = set()
    idx = {}
    low = {}
    out = []

    def visit(v):
        nonlocal index
        idx[v] = low[v] = index
        index += 1
        stack.append(v)
        on.add(v)
        for w in graph[v]:
            if w not in idx:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = stack.pop()
                on.remove(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(sorted(comp))

    for n in nodes:
        if n not in idx:
            visit(n)
    return sorted(out)


@lru_cache(maxsize=1)
def build() -> dict:
    nodes = service_nodes()
    edges = compose_edges(nodes)
    edges += python_edges(nodes)
    edges = [e for e in edges if e["source"] != e["target"]]
    edges = sorted(edges, key=lambda e: (e["source"], e["target"], e["kind"], e["evidence"]))
    incoming = defaultdict(int)
    outgoing = defaultdict(int)
    for e in edges:
        outgoing[e["source"]] += 1
        incoming[e["target"]] += 1
    node_rows = []
    for n in sorted(nodes):
        row = dict(nodes[n])
        row["incoming"] = incoming[n]
        row["outgoing"] = outgoing[n]
        row["orphan"] = incoming[n] + outgoing[n] == 0
        node_rows.append(row)
    cycles = scc([n["id"] for n in node_rows], edges)
    payload = {"schema_version": "1.0.0", "nodes": node_rows, "edges": edges, "cycles": cycles}
    payload["summary"] = {
        "nodes": len(node_rows),
        "edges": len(edges),
        "orphans": sum(n["orphan"] for n in node_rows),
        "cycles": len(cycles),
        "code_edges": sum(e["kind"] == "code-reference" for e in edges),
        "compose_edges": sum(e["kind"] == "compose-depends-on" for e in edges),
    }
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def write(payload: dict):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "architecture_graph.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (OUT / "architecture_edges.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source", "target", "kind", "evidence"])
        w.writeheader()
        w.writerows(payload["edges"])
    with (OUT / "architecture_nodes.csv").open("w", newline="", encoding="utf-8") as fh:
        fields = ["id", "kind", "incoming", "outgoing", "orphan", "paths"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for n in payload["nodes"]:
            w.writerow({**n, "paths": ";".join(n["paths"])})
    s = payload["summary"]
    lines = [
        "# SAHOOL Architecture Graph",
        "",
        "Repository-derived evidence only; runtime activation is not implied.",
        "",
        "## Summary",
        "",
        f"- Nodes: {s['nodes']}",
        f"- Edges: {s['edges']}",
        f"- Code-reference edges: {s['code_edges']}",
        f"- Compose dependency edges: {s['compose_edges']}",
        f"- Orphan nodes: {s['orphans']}",
        f"- Strongly connected components: {s['cycles']}",
        "",
        "## Cycles",
        "",
    ]
    lines += ["- " + " → ".join(c) for c in payload["cycles"]] or [
        "- None detected by this conservative scanner."
    ]
    lines += ["", "## Orphans", ""]
    lines += [f"- {n['id']}" for n in payload["nodes"] if n["orphan"]] or ["- None"]
    (OUT / "ARCHITECTURE_GRAPH_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--generate", action="store_true")
    args = ap.parse_args()
    payload = build()
    target = OUT / "architecture_graph.json"
    if args.check:
        if not target.exists():
            raise SystemExit("FAIL: generated architecture graph is missing")
        current = json.loads(target.read_text(encoding="utf-8"))
        if current != payload:
            raise SystemExit("FAIL: architecture graph drift detected; run --generate")
        print(
            f"PASS: architecture graph stable ({payload['summary']['nodes']} nodes, {payload['summary']['edges']} edges)"
        )
        return
    write(payload)
    print(
        f"PASS: generated architecture graph ({payload['summary']['nodes']} nodes, {payload['summary']['edges']} edges, {payload['summary']['cycles']} cycles)"
    )


if __name__ == "__main__":
    main()

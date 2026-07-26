#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/capability-registry"
INDEX = BASE / "capability_index.yaml"
OUT = BASE / "generated"
ID_RE = re.compile(r"^([A-Z]+)-(\d{3})$")


def load():
    idx = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    domains = []
    caps = []
    for d in idx["domains"]:
        p = BASE / d["file"]
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        domains.append((d, doc, p))
        caps.extend(doc.get("capabilities", []))
    return idx, domains, caps


def validate(idx, domains, caps):
    e = []
    if idx.get("schema_version") != "1.0.0":
        e.append("index schema_version must be 1.0.0")
    keys = [d["key"] for d in idx.get("domains", [])]
    ids = [d["id"] for d in idx.get("domains", [])]
    if len(keys) != len(set(keys)):
        e.append("duplicate domain keys")
    if len(ids) != len(set(ids)):
        e.append("duplicate domain ids")
    prefixes = {
        d["key"]: set(d.get("accepted_prefixes", [d["capability_prefix"]])) for d in idx["domains"]
    }
    capids = [c.get("id") for c in caps]
    for x, n in Counter(capids).items():
        if n > 1:
            e.append(f"duplicate capability id: {x}")
    known = set(capids)
    graph = {}
    voc = idx["controlled_vocabularies"]
    required = [
        "id",
        "title",
        "domain",
        "owner",
        "maturity",
        "evidence_level",
        "status",
        "priority",
        "business_value",
        "investment_strategy",
        "parity_classification",
        "dependencies",
        "services",
        "apis",
        "ui_consumers",
        "mobile_consumers",
        "tests",
        "runtime",
        "production_certified",
    ]
    for d, doc, p in domains:
        dm = doc.get("domain", {})
        for f in ("id", "key", "title", "capability_prefix", "accepted_prefixes"):
            if dm.get(f) != d.get(f):
                e.append(f"{p}: domain {f} mismatch")
        if doc.get("schema_version") != "1.0.0":
            e.append(f"{p}: schema_version must be 1.0.0")
    for c in caps:
        cid = c.get("id", "<missing>")
        for f in required:
            if f not in c:
                e.append(f"{cid}: missing {f}")
        m = ID_RE.match(str(cid))
        dom = c.get("domain")
        if not m:
            e.append(f"{cid}: invalid id format")
        elif dom not in prefixes or m.group(1) not in prefixes[dom]:
            e.append(f"{cid}: prefix does not match domain {dom}")
        t = c.get("title")
        if not isinstance(t, dict) or not str(t.get("en", "")).strip() or "ar" not in t:
            e.append(f"{cid}: bilingual title object required")
        if not isinstance(c.get("maturity"), int) or not 0 <= c["maturity"] <= 5:
            e.append(f"{cid}: maturity must be 0..5")
        if not isinstance(c.get("evidence_level"), int) or not 0 <= c["evidence_level"] <= 5:
            e.append(f"{cid}: evidence_level must be 0..5")
        for f in ("priority", "business_value", "investment_strategy", "parity_classification"):
            if c.get(f) not in voc[f]:
                e.append(f"{cid}: invalid {f}: {c.get(f)}")
        for f in (
            "dependencies",
            "services",
            "apis",
            "ui_consumers",
            "mobile_consumers",
            "tests",
            "roadmap_refs",
            "workflow_refs",
        ):
            v = c.get(f, [])
            if not isinstance(v, list):
                e.append(f"{cid}: {f} must be list")
            elif len(v) != len(set(map(str, v))):
                e.append(f"{cid}: duplicate values in {f}")
        for dep in c.get("dependencies", []):
            if dep not in known:
                e.append(f"{cid}: unknown dependency {dep}")
            if dep == cid:
                e.append(f"{cid}: self dependency")
        for f in ("services", "ui_consumers", "mobile_consumers", "tests"):
            for path in c.get(f, []):
                if not (ROOT / path).exists():
                    e.append(f"{cid}: missing repository path {path}")
        if c.get("production_certified"):
            if c.get("maturity") != 5 or c.get("evidence_level") != 5:
                e.append(f"{cid}: certification requires maturity/evidence 5")
        graph[cid] = c.get("dependencies", [])
    indeg = {n: 0 for n in graph}
    rev = defaultdict(list)
    for n, deps in graph.items():
        for d in deps:
            if d in graph:
                indeg[n] += 1
                rev[d].append(n)
    q = deque(n for n, v in indeg.items() if v == 0)
    seen = 0
    while q:
        n = q.popleft()
        seen += 1
        for z in rev[n]:
            indeg[z] -= 1
            if indeg[z] == 0:
                q.append(z)
    if seen != len(graph):
        e.append("capability graph contains cycle")
    return e


def canonical(idx, caps):
    return {
        "schema_version": "1.0.0",
        "registry_name": idx["registry_name"],
        "domains": idx["domains"],
        "capabilities": sorted(caps, key=lambda c: c["id"]),
    }


def generate(idx, caps):
    OUT.mkdir(parents=True, exist_ok=True)
    reg = canonical(idx, caps)
    blob = json.dumps(reg, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    (OUT / "capability_registry.json").write_text(
        json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    summary = {
        "schema_version": "1.0.0",
        "capabilities_total": len(caps),
        "domains_total": len(idx["domains"]),
        "registry_sha256": hashlib.sha256(blob).hexdigest(),
        "by_domain": dict(sorted(Counter(c["domain"] for c in caps).items())),
        "by_maturity": {str(k): v for k, v in sorted(Counter(c["maturity"] for c in caps).items())},
        "unassessed_priority": sum(c["priority"] == "unassessed" for c in caps),
        "unassessed_parity": sum(c["parity_classification"] == "unassessed" for c in caps),
        "production_certified": sum(bool(c["production_certified"]) for c in caps),
    }
    (OUT / "capability_registry_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (OUT / "capability_registry.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "id",
            "title_en",
            "title_ar",
            "domain",
            "owner",
            "maturity",
            "evidence_level",
            "priority",
            "business_value",
            "investment_strategy",
            "parity_classification",
            "status",
            "production_certified",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in sorted(caps, key=lambda x: x["id"]):
            w.writerow(
                {
                    **{k: c.get(k, "") for k in fields if not k.startswith("title_")},
                    "title_en": c["title"]["en"],
                    "title_ar": c["title"]["ar"],
                }
            )
    graph = {
        "nodes": [
            {
                "id": c["id"],
                "domain": c["domain"],
                "title": c["title"]["en"],
                "maturity": c["maturity"],
            }
            for c in sorted(caps, key=lambda x: x["id"])
        ],
        "edges": [
            {"from": d, "to": c["id"], "type": "depends_on"}
            for c in caps
            for d in c.get("dependencies", [])
        ],
    }
    (OUT / "capability_graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# Capability Registry v1 Summary",
        "",
        f"- Capabilities: **{summary['capabilities_total']}**",
        f"- Domains: **{summary['domains_total']}**",
        f"- Production certified: **{summary['production_certified']}**",
        f"- Unassessed priority: **{summary['unassessed_priority']}**",
        f"- Unassessed parity: **{summary['unassessed_parity']}**",
        "",
        "## Domain inventory",
        "",
        "| Domain | Capabilities |",
        "|---|---:|",
    ]
    lines += [f"| {k} | {v} |" for k, v in summary["by_domain"].items()]
    (OUT / "CAPABILITY_REGISTRY_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--generate", action="store_true")
    a = p.parse_args(argv)
    idx, domains, caps = load()
    errs = validate(idx, domains, caps)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    if a.check:
        expected = canonical(idx, caps)
        target = OUT / "capability_registry.json"
        if not target.exists() or json.loads(target.read_text(encoding="utf-8")) != expected:
            print("generated capability registry drift; run --generate", file=sys.stderr)
            return 1
    if a.generate or not a.check:
        generate(idx, caps)
    print(f"capability_registry_v1_ok capabilities={len(caps)} domains={len(idx['domains'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

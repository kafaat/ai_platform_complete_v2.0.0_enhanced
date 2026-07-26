#!/usr/bin/env python3
"""Generate capability traceability and gap reports from the canonical registry."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
OUT = ROOT / "capabilities/generated"


def main() -> int:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    caps = data["capabilities"]
    rows = []
    domain = defaultdict(
        lambda: Counter(total=0, service=0, api=0, test=0, ui=0, mobile=0, owner=0)
    )
    for c in caps:
        d = domain[c["domain"]]
        d["total"] += 1
        values = {
            "service": bool(c.get("services")),
            "api": bool(c.get("apis")),
            "test": bool(c.get("tests")),
            "ui": bool(c.get("ui_consumers")),
            "mobile": bool(c.get("mobile_consumers")),
            "owner": c.get("owner") != "UNASSIGNED",
        }
        for k, present in values.items():
            d[k] += int(present)
        score = round(100 * sum(values.values()) / len(values))
        rows.append(
            {
                "id": c["id"],
                "title": c["title"],
                "domain": c["domain"],
                "owner": c["owner"],
                "services": len(c.get("services", [])),
                "apis": len(c.get("apis", [])),
                "tests": len(c.get("tests", [])),
                "ui_consumers": len(c.get("ui_consumers", [])),
                "mobile_consumers": len(c.get("mobile_consumers", [])),
                "evidence": len(c.get("evidence", [])),
                "traceability_score": score,
                "gaps": ",".join(k for k, present in values.items() if not present),
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "capability_traceability.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "capabilities_total": len(caps),
        "linked_to_service": sum(bool(c.get("services")) for c in caps),
        "linked_to_api": sum(bool(c.get("apis")) for c in caps),
        "linked_to_test": sum(bool(c.get("tests")) for c in caps),
        "linked_to_ui": sum(bool(c.get("ui_consumers")) for c in caps),
        "linked_to_mobile": sum(bool(c.get("mobile_consumers")) for c in caps),
        "assigned_owner": sum(c.get("owner") != "UNASSIGNED" for c in caps),
        "fully_traceable": sum(r["traceability_score"] == 100 for r in rows),
        "zero_traceability": sorted(r["id"] for r in rows if r["traceability_score"] == 0),
        "domain_coverage": {
            name: {k: v for k, v in counts.items()}
            | {
                f"{k}_pct": round(100 * counts[k] / counts["total"], 1)
                for k in ("service", "api", "test", "ui", "mobile", "owner")
            }
            for name, counts in sorted(domain.items())
        },
    }
    (OUT / "capability_traceability_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lowest = sorted(rows, key=lambda r: (r["traceability_score"], r["id"]))[:20]
    md = [
        "# SAHOOL Capability Traceability Report",
        "",
        "Generated from the canonical capability registry. Links are repository evidence, not runtime certification.",
        "",
        "## Coverage",
        "",
        f"- Capabilities: **{summary['capabilities_total']}**",
        f"- Service linked: **{summary['linked_to_service']}**",
        f"- API linked: **{summary['linked_to_api']}**",
        f"- Test linked: **{summary['linked_to_test']}**",
        f"- UI linked: **{summary['linked_to_ui']}**",
        f"- Mobile linked: **{summary['linked_to_mobile']}**",
        f"- Owner assigned: **{summary['assigned_owner']}**",
        f"- Fully traceable across all six surfaces: **{summary['fully_traceable']}**",
        "",
        "## Lowest traceability capabilities",
        "",
        "| ID | Capability | Score | Missing surfaces |",
        "|---|---|---:|---|",
    ]
    for row in lowest:
        md.append(
            f"| {row['id']} | {row['title']} | {row['traceability_score']} | {row['gaps'] or 'none'} |"
        )
    md += [
        "",
        "## Interpretation",
        "",
        "A missing UI or mobile link is not automatically a defect: some capabilities are intentionally backend-only. "
        "Production maturity remains unchanged until runtime metrics, traces, receipts and audit evidence are supplied.",
    ]
    (OUT / "CAPABILITY_TRACEABILITY_REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

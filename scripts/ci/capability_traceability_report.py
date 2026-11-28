#!/usr/bin/env python3
"""Generate traceability reports from the field-authority-resolved capability view."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from capability_authority_view import load_authoritative_capabilities
    from generated_artifact_contract import Artifact, drift, write_all
except ModuleNotFoundError:
    from scripts.ci.capability_authority_view import load_authoritative_capabilities
    from scripts.ci.generated_artifact_contract import Artifact, drift, write_all

# Keep report output and drift diagnostics usable under CI's C locale.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "capabilities/generated"


def artifacts() -> tuple[list[Artifact], dict]:
    """Render all three reports from the same authoritative inputs, without writing."""
    caps = load_authoritative_capabilities(ROOT)
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

    # Preserve this report's historical CSV bytes, including CRLF records.
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=list(rows[0]))
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
    lowest = sorted(rows, key=lambda r: (r["traceability_score"], r["id"]))[:20]
    md = [
        "# SAHOOL Capability Traceability Report",
        "",
        "Generated from the field-authority-resolved capability view. Canonical definition fields come from Registry v1; repository links remain projections and are not runtime certification.",
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
    return [
        Artifact(OUT / "capability_traceability.csv", csv_buffer.getvalue()),
        Artifact(
            OUT / "capability_traceability_summary.json",
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        ),
        Artifact(OUT / "CAPABILITY_TRACEABILITY_REPORT.md", "\n".join(md) + "\n"),
    ], summary


def main(*, check: bool = False) -> int:
    rendered, summary = artifacts()
    if check:
        changed = drift(rendered)
        if changed:
            print("Capability traceability report drift: " + " · ".join(changed), file=sys.stderr)
            return 1
    else:
        write_all(rendered)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare every report without writing")
    raise SystemExit(main(check=parser.parse_args().check))

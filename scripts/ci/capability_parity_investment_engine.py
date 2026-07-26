#!/usr/bin/env python3
"""Generate fail-closed capability parity and investment artifacts.

Official vendor pages prove product claims, not numeric maturity. Competitor scores in this
engine are provisional analyst applications of the repository rubric and only direct,
canonical capability mappings can affect parity.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/capability-registry/generated/capability_registry.json"
MATURITY = ROOT / "docs/capability-registry/generated/evidence/capability_maturity_baseline.json"
SOURCE_DIR = ROOT / "docs/capability-registry/benchmark/source"
SAHOOL_ASSESSMENTS = SOURCE_DIR / "sahool_capability_assessments.csv"
DECISIONS = SOURCE_DIR / "build_integrate_partner_matrix.csv"
EVIDENCE = SOURCE_DIR / "competitor_official_evidence.csv"
CANONICALIZATION = SOURCE_DIR / "canonicalization_map_v3_to_registry_v1.csv"
RUBRIC = ROOT / "docs/capability-registry/benchmark/BENCHMARK_SCORING_RUBRIC.md"
LEGACY_INPUTS = [
    SOURCE_DIR / "legacy/competitive_benchmark_matrix_v3_precanonical.csv",
    SOURCE_DIR / "legacy/competitor_official_evidence_precanonical.csv",
    SOURCE_DIR / "legacy/build_integrate_partner_matrix_precanonical.csv",
]
OUT = ROOT / "docs/capability-registry/generated/benchmark"
OUTPUT_FILES = [
    "capability_parity_matrix.json",
    "capability_parity_matrix.csv",
    "capability_investment_matrix.json",
    "capability_investment_matrix.csv",
    "domain_heat_map.json",
    "CAPABILITY_PARITY_INVESTMENT_REPORT.md",
]
PLATFORMS = ["FieldView", "CropX", "GeoPard", "Cropwise", "EOSDA", "OneSoil", "Farmonaut"]
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
ALLOWED_VERDICTS = {"PROVISIONAL", "PARTIAL", "CONFIRMED_MISSING"}
ALLOWED_SCOPES = {"direct", "adjacent"}


class InputError(ValueError):
    """Raised when a benchmark input violates the fail-closed contract."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def dump_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_score(raw: str, *, context: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{context}: score must be an integer from 0 to 5") from exc
    if not 0 <= value <= 5:
        raise InputError(f"{context}: score {value} is outside 0..5")
    return value


def split_semicolon(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(";") if part.strip()]


def registry_index() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    registry = load_json(REGISTRY)
    capabilities = registry.get("capabilities", [])
    by_id = {cap["id"]: cap for cap in capabilities}
    if len(by_id) != len(capabilities):
        raise InputError("canonical registry contains duplicate capability IDs")
    return registry, by_id


def validate_canonical_fields(
    row: dict[str, str],
    registry: dict[str, dict[str, Any]],
    *,
    context: str,
) -> str:
    capability_id = row.get("capability_id", "").strip()
    if capability_id not in registry:
        raise InputError(f"{context}: unknown capability_id {capability_id!r}")
    canonical = registry[capability_id]
    if row.get("canonical_title", "").strip() != canonical["title"]["en"]:
        raise InputError(
            f"{context}: title mismatch for {capability_id}: "
            f"{row.get('canonical_title')!r} != {canonical['title']['en']!r}"
        )
    if row.get("domain", "").strip() != canonical["domain"]:
        raise InputError(
            f"{context}: domain mismatch for {capability_id}: "
            f"{row.get('domain')!r} != {canonical['domain']!r}"
        )
    return capability_id


def load_sahool_assessments(registry: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows = load_csv(SAHOOL_ASSESSMENTS)
    result: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows, start=2):
        context = f"{SAHOOL_ASSESSMENTS.relative_to(ROOT)}:{number}"
        capability_id = validate_canonical_fields(row, registry, context=context)
        if capability_id in result:
            raise InputError(f"{context}: duplicate SAHOOL assessment for {capability_id}")
        verdict = row.get("verdict", "").strip()
        confidence = row.get("confidence", "").strip()
        if verdict not in ALLOWED_VERDICTS:
            raise InputError(f"{context}: invalid verdict {verdict!r}")
        if confidence not in CONFIDENCE_ORDER:
            raise InputError(f"{context}: invalid confidence {confidence!r}")
        result[capability_id] = {
            **row,
            "sahool_score": parse_score(row.get("sahool_score", ""), context=context),
        }
    return result


def load_competitor_evidence(
    registry: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    rows = load_csv(EVIDENCE)
    evidence_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for number, row in enumerate(rows, start=2):
        context = f"{EVIDENCE.relative_to(ROOT)}:{number}"
        evidence_id = row.get("evidence_id", "").strip()
        if not evidence_id or evidence_id in evidence_ids:
            raise InputError(f"{context}: missing or duplicate evidence_id {evidence_id!r}")
        evidence_ids.add(evidence_id)
        capability_id = validate_canonical_fields(row, registry, context=context)
        platform = row.get("platform", "").strip()
        if platform not in PLATFORMS:
            raise InputError(f"{context}: unsupported platform {platform!r}")
        confidence = row.get("confidence", "").strip()
        if confidence not in CONFIDENCE_ORDER:
            raise InputError(f"{context}: invalid confidence {confidence!r}")
        scope = row.get("comparison_scope", "").strip()
        if scope not in ALLOWED_SCOPES:
            raise InputError(f"{context}: invalid comparison_scope {scope!r}")
        url = row.get("url", "").strip()
        if not url.startswith("https://"):
            raise InputError(f"{context}: official evidence URL must use https")
        raw_score = row.get("analyst_score", "").strip()
        score: int | None
        if scope == "direct":
            score = parse_score(raw_score, context=context)
        else:
            if raw_score:
                raise InputError(f"{context}: adjacent evidence cannot carry a parity score")
            score = None
        item = {
            **row,
            "capability_id": capability_id,
            "platform": platform,
            "confidence": confidence,
            "comparison_scope": scope,
            "analyst_score": score,
        }
        normalized.append(item)
        if scope == "direct":
            grouped[(capability_id, platform)].append(item)

    score_map: dict[tuple[str, str], dict[str, Any]] = {}
    for key, items in grouped.items():
        scores = {item["analyst_score"] for item in items}
        if len(scores) != 1:
            cid, platform = key
            raise InputError(f"conflicting direct scores for {cid}/{platform}: {sorted(scores)}")
        confidence = min(items, key=lambda item: CONFIDENCE_ORDER[item["confidence"]])["confidence"]
        score_map[key] = {
            "score": next(iter(scores)),
            "evidence_refs": sorted(item["evidence_id"] for item in items),
            "confidence": confidence,
            "verification_statuses": sorted({item["verification_status"] for item in items}),
        }
    return normalized, score_map


def load_decisions(
    registry: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = load_csv(DECISIONS)
    decision_ids: set[str] = set()
    assignments: dict[str, dict[str, Any]] = {}
    normalized: list[dict[str, Any]] = []
    for number, row in enumerate(rows, start=2):
        context = f"{DECISIONS.relative_to(ROOT)}:{number}"
        decision_id = row.get("decision_id", "").strip()
        if not decision_id or decision_id in decision_ids:
            raise InputError(f"{context}: missing or duplicate decision_id {decision_id!r}")
        decision_ids.add(decision_id)
        capability_ids = split_semicolon(row.get("target_capability_ids", ""))
        titles = split_semicolon(row.get("canonical_titles", ""))
        if not capability_ids or len(capability_ids) != len(titles):
            raise InputError(
                f"{context}: target IDs and canonical titles must be non-empty and aligned"
            )
        for capability_id, title in zip(capability_ids, titles, strict=True):
            if capability_id not in registry:
                raise InputError(f"{context}: unknown target capability {capability_id}")
            expected_title = registry[capability_id]["title"]["en"]
            if title != expected_title:
                raise InputError(
                    f"{context}: title mismatch for {capability_id}: {title!r} != {expected_title!r}"
                )
            if capability_id in assignments:
                raise InputError(
                    f"{context}: capability {capability_id} has multiple approved decisions"
                )
            assignments[capability_id] = {
                **row,
                "decision_id": decision_id,
                "capability_id": capability_id,
                "canonical_title": title,
            }
        normalized.append(
            {**row, "target_capability_ids": capability_ids, "canonical_titles": titles}
        )
    return normalized, assignments


def classify(sahool_score: int, competitor_best: int | None) -> str:
    if competitor_best is None:
        return "Unassessed"
    if sahool_score == 0 and competitor_best > 0:
        return "Missing"
    if sahool_score > competitor_best:
        return "Leader"
    if sahool_score == competitor_best:
        return "Parity"
    return "Behind"


def derived_investment(
    capability_id: str,
    parity: str,
    domain: str,
    assignments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if capability_id in assignments:
        row = assignments[capability_id]
        return {
            "decision_id": row["decision_id"],
            "decision": row["decision"],
            "priority": row["priority"],
            "decision_source": "approved_phase3_decision",
            "reason": row["reason"],
            "next_gate": row["next_gate"],
            "approved": True,
        }
    if parity == "Unassessed":
        return {
            "decision_id": None,
            "decision": "UNASSESSED",
            "priority": "UNASSESSED",
            "decision_source": "competitor_evidence_missing",
            "reason": "No direct, canonical competitor baseline exists for this capability.",
            "next_gate": "Collect official direct-comparison evidence before an investment commitment.",
            "approved": False,
        }
    if parity == "Leader":
        return {
            "decision_id": None,
            "decision": "BUILD/LEAD",
            "priority": "P2",
            "decision_source": "parity_policy",
            "reason": "Preserve the provisional lead while preventing evidence drift.",
            "next_gate": "Add runtime and production evidence before claiming certification.",
            "approved": False,
        }
    if parity == "Parity":
        return {
            "decision_id": None,
            "decision": "MAINTAIN",
            "priority": "P2",
            "decision_source": "parity_policy",
            "reason": "The capability is at provisional evidence-linked parity.",
            "next_gate": "Close runtime evidence and regression coverage gaps.",
            "approved": False,
        }
    if parity in {"Behind", "Missing"} and domain in {"decision", "security", "irrigation"}:
        return {
            "decision_id": None,
            "decision": "BUILD",
            "priority": "P1",
            "decision_source": "strategic_domain_policy",
            "reason": "This is a strategic SAHOOL control-plane or regional agronomy capability.",
            "next_gate": "Define a capability-owned delivery slice and acceptance evidence.",
            "approved": False,
        }
    if parity in {"Behind", "Missing"}:
        return {
            "decision_id": None,
            "decision": "REVIEW BUILD VS INTEGRATE",
            "priority": "P1",
            "decision_source": "gap_policy",
            "reason": "A provisional competitive gap exists, but sourcing requires architecture review.",
            "next_gate": "Record an ADR choosing build, integrate or partner with cost and lock-in evidence.",
            "approved": False,
        }
    raise InputError(f"no safe investment policy for {capability_id}/{parity}")


def build() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry_data, registry = registry_index()
    maturity_data = load_json(MATURITY)
    maturity = {row["capability_id"]: row for row in maturity_data.get("capabilities", [])}
    if set(maturity) != set(registry):
        missing = sorted(set(registry) - set(maturity))
        extra = sorted(set(maturity) - set(registry))
        raise InputError(f"maturity baseline ID drift; missing={missing}, extra={extra}")

    assessments = load_sahool_assessments(registry)
    evidence_rows, score_map = load_competitor_evidence(registry)
    decision_rows, assignments = load_decisions(registry)

    parity_rows: list[dict[str, Any]] = []
    investment_rows: list[dict[str, Any]] = []
    for capability in sorted(registry_data["capabilities"], key=lambda row: row["id"]):
        capability_id = capability["id"]
        assessment = assessments.get(capability_id)
        sahool_score = (
            assessment["sahool_score"]
            if assessment
            else int(maturity[capability_id]["assessed_maturity"])
        )
        scores: dict[str, int | None] = {}
        refs: dict[str, list[str]] = {}
        confidences: dict[str, str | None] = {}
        verification: dict[str, list[str]] = {}
        for platform in PLATFORMS:
            scored = score_map.get((capability_id, platform))
            scores[platform] = scored["score"] if scored else None
            refs[platform] = scored["evidence_refs"] if scored else []
            confidences[platform] = scored["confidence"] if scored else None
            verification[platform] = scored["verification_statuses"] if scored else []
        competitor_values = [score for score in scores.values() if score is not None]
        competitor_best = max(competitor_values) if competitor_values else None
        parity_class = classify(sahool_score, competitor_best)
        parity_row = {
            "capability_id": capability_id,
            "title": capability["title"]["en"],
            "domain": capability["domain"],
            "sahool_score": sahool_score,
            "sahool_score_source": "phase3_canonical_assessment"
            if assessment
            else "evidence_maturity_baseline",
            "sahool_score_confidence": assessment["confidence"]
            if assessment
            else "repository_static",
            "competitor_scores": scores,
            "competitor_evidence_refs": refs,
            "competitor_score_confidence": confidences,
            "competitor_verification_status": verification,
            "best_evidenced_competitor_score": competitor_best,
            "gap_to_best": None if competitor_best is None else competitor_best - sahool_score,
            "classification": parity_class,
            "benchmark_coverage": "evidence_linked_provisional"
            if competitor_best is not None
            else "unassessed",
            "runtime_verified": False,
            "production_certified": False,
        }
        parity_rows.append(parity_row)
        investment = derived_investment(
            capability_id, parity_class, capability["domain"], assignments
        )
        investment_rows.append(
            {
                "capability_id": capability_id,
                "title": capability["title"]["en"],
                "domain": capability["domain"],
                "parity_classification": parity_class,
                **investment,
            }
        )

    classifications = {
        name: sum(row["classification"] == name for row in parity_rows)
        for name in ["Leader", "Parity", "Behind", "Missing", "Unassessed"]
    }
    direct_evidence = [row for row in evidence_rows if row["comparison_scope"] == "direct"]
    adjacent_evidence = [row for row in evidence_rows if row["comparison_scope"] == "adjacent"]
    summary = {
        "capabilities": len(parity_rows),
        "evidence_linked_benchmarks": sum(
            row["benchmark_coverage"] == "evidence_linked_provisional" for row in parity_rows
        ),
        "unassessed": sum(row["benchmark_coverage"] == "unassessed" for row in parity_rows),
        "direct_evidence_rows": len(direct_evidence),
        "adjacent_evidence_rows_excluded_from_scores": len(adjacent_evidence),
        "decision_records": len(decision_rows),
        "approved_capability_assignments": len(assignments),
        "classifications": classifications,
        "runtime_verified": 0,
        "production_certified": 0,
    }

    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in parity_rows:
        by_domain[row["domain"]].append(row)
    heat_rows: list[dict[str, Any]] = []
    for domain, rows in sorted(by_domain.items()):
        benchmarked = [
            row for row in rows if row["benchmark_coverage"] == "evidence_linked_provisional"
        ]
        heat_rows.append(
            {
                "domain": domain,
                "capability_count": len(rows),
                "benchmarked_count": len(benchmarked),
                "benchmark_coverage_pct": round(100 * len(benchmarked) / len(rows), 1),
                "average_sahool_maturity": round(
                    sum(maturity[row["capability_id"]]["assessed_maturity"] for row in rows)
                    / len(rows),
                    2,
                ),
                "parity_counts": {
                    name: sum(row["classification"] == name for row in rows)
                    for name in ["Leader", "Parity", "Behind", "Missing", "Unassessed"]
                },
            }
        )

    parity = {
        "schema_version": "2.0.0",
        "scoring_model": "provisional_analyst_score_from_direct_official_evidence",
        "summary": summary,
        "capabilities": parity_rows,
    }
    investment = {
        "schema_version": "2.0.0",
        "summary": summary,
        "capabilities": investment_rows,
    }
    heat = {"schema_version": "2.0.0", "summary": summary, "domains": heat_rows}
    return parity, investment, heat


def render_csv(
    rows: list[dict[str, Any]], fields: list[str], json_fields: set[str] | None = None
) -> bytes:
    json_fields = json_fields or set()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        output = {field: row.get(field) for field in fields}
        for field in json_fields:
            output[field] = json.dumps(output[field], ensure_ascii=False, sort_keys=True)
        writer.writerow(output)
    return buffer.getvalue().encode()


def render_outputs() -> dict[str, bytes]:
    parity, investment, heat = build()
    outputs: dict[str, bytes] = {
        "capability_parity_matrix.json": dump_json(parity),
        "capability_investment_matrix.json": dump_json(investment),
        "domain_heat_map.json": dump_json(heat),
    }
    outputs["capability_parity_matrix.csv"] = render_csv(
        parity["capabilities"],
        [
            "capability_id",
            "title",
            "domain",
            "sahool_score",
            "sahool_score_source",
            "sahool_score_confidence",
            "competitor_scores",
            "competitor_evidence_refs",
            "competitor_score_confidence",
            "best_evidenced_competitor_score",
            "gap_to_best",
            "classification",
            "benchmark_coverage",
            "runtime_verified",
            "production_certified",
        ],
        {"competitor_scores", "competitor_evidence_refs", "competitor_score_confidence"},
    )
    outputs["capability_investment_matrix.csv"] = render_csv(
        investment["capabilities"],
        [
            "capability_id",
            "title",
            "domain",
            "parity_classification",
            "decision_id",
            "decision",
            "priority",
            "decision_source",
            "reason",
            "next_gate",
            "approved",
        ],
    )
    summary = parity["summary"]
    lines = [
        "# Capability Parity & Investment Baseline",
        "",
        "> Scores are provisional analyst applications of the benchmark rubric. Official vendor pages prove product claims; they do not issue these maturity scores.",
        "",
        f"- Canonical capabilities: **{summary['capabilities']}**",
        f"- Direct evidence-linked competitor benchmarks: **{summary['evidence_linked_benchmarks']}**",
        f"- Unassessed: **{summary['unassessed']}**",
        f"- Direct official-evidence rows: **{summary['direct_evidence_rows']}**",
        f"- Adjacent evidence excluded from parity: **{summary['adjacent_evidence_rows_excluded_from_scores']}**",
        f"- Approved decision records: **{summary['decision_records']}**",
        f"- Approved capability assignments: **{summary['approved_capability_assignments']}**",
        f"- Leader / Parity / Behind / Missing: **{summary['classifications']['Leader']} / {summary['classifications']['Parity']} / {summary['classifications']['Behind']} / {summary['classifications']['Missing']}**",
        "- Runtime verified: **0**",
        "- Production certified: **0**",
        "",
        "## Domain heat map",
        "",
        "| Domain | Capabilities | Benchmarked | Coverage | Repository maturity | Leader | Parity | Behind | Missing |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for domain in heat["domains"]:
        counts = domain["parity_counts"]
        lines.append(
            f"| {domain['domain']} | {domain['capability_count']} | {domain['benchmarked_count']} | "
            f"{domain['benchmark_coverage_pct']}% | {domain['average_sahool_maturity']} | "
            f"{counts['Leader']} | {counts['Parity']} | {counts['Behind']} | {counts['Missing']} |"
        )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "- Only direct canonical mappings affect parity.",
            "- ETa is retained as adjacent evidence and is not scored as ET0.",
            "- Missing competitor evidence remains `Unassessed`.",
            "- Repository maturity is not competitor evidence.",
            "- No runtime or production claim is produced by this engine.",
            "",
        ]
    )
    outputs["CAPABILITY_PARITY_INVESTMENT_REPORT.md"] = "\n".join(lines).encode()
    return outputs


def expected_manifest(outputs: dict[str, bytes]) -> dict[str, Any]:
    inputs = [
        REGISTRY,
        MATURITY,
        SAHOOL_ASSESSMENTS,
        DECISIONS,
        EVIDENCE,
        CANONICALIZATION,
        RUBRIC,
        *LEGACY_INPUTS,
    ]
    return {
        "schema_version": "2.0.0",
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in inputs},
        "outputs": {
            name: hashlib.sha256(data).hexdigest() for name, data in sorted(outputs.items())
        },
    }


def write(outputs: dict[str, bytes]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        (OUT / name).write_bytes(data)
    (OUT / "benchmark_manifest.json").write_bytes(dump_json(expected_manifest(outputs)))


def check(outputs: dict[str, bytes]) -> list[str]:
    errors: list[str] = []
    for name, data in outputs.items():
        path = OUT / name
        if not path.exists():
            errors.append(f"missing:{name}")
        elif path.read_bytes() != data:
            errors.append(f"drift:{name}")
    manifest_path = OUT / "benchmark_manifest.json"
    manifest = expected_manifest(outputs)
    if not manifest_path.exists():
        errors.append("missing:benchmark_manifest.json")
    elif load_json(manifest_path) != manifest:
        errors.append("drift:benchmark_manifest.json")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        outputs = render_outputs()
    except Exception as exc:  # fail closed with a concise CI diagnostic
        print(f"Capability parity/investment input error: {exc}", file=sys.stderr)
        return 2
    if args.generate:
        write(outputs)
        parity = json.loads(outputs["capability_parity_matrix.json"])
        print(
            "Capability parity/investment generated: "
            f"{parity['summary']['evidence_linked_benchmarks']}/{parity['summary']['capabilities']} benchmarked"
        )
        return 0
    errors = check(outputs)
    if errors:
        print("Capability parity/investment drift:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    parity = json.loads(outputs["capability_parity_matrix.json"])
    print(
        "Capability parity/investment: PASS — "
        f"{parity['summary']['evidence_linked_benchmarks']}/{parity['summary']['capabilities']} benchmarked; "
        f"{parity['summary']['unassessed']} unassessed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

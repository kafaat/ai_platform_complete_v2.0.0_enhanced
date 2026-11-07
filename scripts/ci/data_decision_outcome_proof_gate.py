#!/usr/bin/env python3
"""Read-only integrity gate for a *plan* of SAHOOL end-to-end evidence.

This gate verifies source references and submitted artifact *bytes* only. It does
NOT authenticate field observations, attest a staging run, or approve deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "sahool.data-decision-outcome-proof/v1"
EXPECTED_IDS = (
    "S01_EO_INGEST",
    "S02_WEATHER_ET0",
    "S03_FIELD_CONTEXT",
    "S04_WATER_LEDGER",
    "S05_DECISION_APPROVAL",
    "S06_EXECUTION",
    "S07_OUTCOME",
    "S08_CALIBRATION",
    "S09_LEARNING_RELEASE",
)
STATES = {"NOT_RUN", "FAILED", "EVIDENCE_SUBMITTED"}
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _safe_file(root: Path, path: Any, *, prefix: str | None = None) -> Path:
    if not isinstance(path, str) or not path or "\\" in path:
        raise ValueError("invalid_repository_path")
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        raise ValueError("path_escape_rejected")
    if prefix and not path.startswith(prefix):
        raise ValueError("evidence_outside_dedicated_directory")
    candidate = (root / rel).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError("missing_or_escaping_file")
    return candidate


def validate(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        return {
            "schema": SCHEMA,
            "manifest_valid": False,
            "complete_e3": False,
            "e3_review_candidate": False,
            "source_review_only": True,
            "stages": [],
            "errors": ["manifest_root_not_object"],
        }
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append("invalid_schema")
    if not COMMIT_SHA.fullmatch(str(manifest.get("baseline_commit", ""))):
        errors.append("invalid_baseline_commit")
    if manifest.get("production_mutations_allowed") is not False:
        errors.append("production_mutations_must_be_disabled")
    if manifest.get("promotion_policy") != "independent_approval_required":
        errors.append("independent_promotion_required")
    stages = manifest.get("stages")
    if (
        not isinstance(stages, list)
        or [x.get("id") for x in stages if isinstance(x, dict)] != list(EXPECTED_IDS)
        or len(stages) != len(EXPECTED_IDS)
    ):
        errors.append("stages_missing_reordered_or_duplicated")
        stages = [] if not isinstance(stages, list) else stages
    report: list[dict[str, Any]] = []
    for stage in stages:
        if not isinstance(stage, dict):
            errors.append("invalid_stage")
            continue
        sid = str(stage.get("id", "?"))
        paths = stage.get("source_paths")
        if not isinstance(paths, list) or not paths or len(paths) != len(set(map(str, paths))):
            errors.append(f"{sid}:invalid_source_paths")
            paths = []
        for source in paths:
            try:
                _safe_file(root, source)
            except ValueError as exc:
                errors.append(f"{sid}:source:{exc}")
        if any(
            not isinstance(stage.get(k), str) or not stage[k].strip()
            for k in ("name_ar", "authority", "acceptance")
        ):
            errors.append(f"{sid}:missing_contract")
        state = stage.get("e3_state")
        if not isinstance(state, str) or state not in STATES:
            errors.append(f"{sid}:invalid_e3_state")
        receipt = stage.get("receipt")
        if state == "NOT_RUN" and receipt is not None:
            errors.append(f"{sid}:not_run_has_receipt")
        if isinstance(state, str) and state in {"FAILED", "EVIDENCE_SUBMITTED"}:
            if not isinstance(receipt, dict):
                errors.append(f"{sid}:missing_receipt")
            else:
                if receipt.get("result") != ("FAIL" if state == "FAILED" else "PASS"):
                    errors.append(f"{sid}:result_state_mismatch")
                if not isinstance(receipt.get("environment"), str) or receipt[
                    "environment"
                ] not in {"ci", "staging", "field"}:
                    errors.append(f"{sid}:invalid_environment")
                if not COMMIT_SHA.fullmatch(str(receipt.get("source_commit", ""))):
                    errors.append(f"{sid}:invalid_receipt_source_commit")
                digest = receipt.get("sha256")
                if not isinstance(digest, str) or not HEX_SHA.fullmatch(digest):
                    errors.append(f"{sid}:invalid_receipt_digest")
                try:
                    artifact = _safe_file(
                        root,
                        receipt.get("artifact_path"),
                        prefix="certification/evidence/data_decision_outcome/",
                    )
                    if (
                        isinstance(digest, str)
                        and hashlib.sha256(artifact.read_bytes()).hexdigest() != digest
                    ):
                        errors.append(f"{sid}:receipt_digest_mismatch")
                except ValueError as exc:
                    errors.append(f"{sid}:receipt:{exc}")
        report.append({"stage": sid, "source_paths": len(paths), "e3_state": state})
    all_submitted = len(report) == len(EXPECTED_IDS) and all(
        x["e3_state"] == "EVIDENCE_SUBMITTED" for x in report
    )
    return {
        "schema": SCHEMA,
        "manifest_valid": not errors,
        "complete_e3": False,
        "e3_review_candidate": all_submitted and not errors,
        "reason": (
            "INDEPENDENT_ACCEPTANCE_NOT_PERFORMED"
            if all_submitted and not errors
            else "E3_EVIDENCE_INCOMPLETE"
        ),
        "source_review_only": True,
        "stages": report,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--require-e3",
        action="store_true",
        help="Fail until separate independent E3 acceptance exists",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest_path = args.manifest or root / "config/proof/data_decision_outcome_v1.json"
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        report = validate(document, root)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        report = {
            "schema": SCHEMA,
            "manifest_valid": False,
            "complete_e3": False,
            "errors": [f"manifest_error:{type(exc).__name__}"],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["manifest_valid"]:
        return 1
    if args.require_e3:
        return 2  # This integrity checker never confers E3 certification.
    return 0


if __name__ == "__main__":
    sys.exit(main())

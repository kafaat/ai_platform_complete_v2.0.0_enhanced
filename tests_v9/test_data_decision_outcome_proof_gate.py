"""Negative and positive tests for the source-only evidence integrity guard."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ci/data_decision_outcome_proof_gate.py"
_spec = importlib.util.spec_from_file_location("data_decision_outcome_proof_gate", _SCRIPT)
assert _spec and _spec.loader
_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gate)


class ProofGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        stages = []
        for stage_id in _gate.EXPECTED_IDS:
            path = f"services/{stage_id.lower()}.py"
            fp = self.root / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text("# source fixture\n", encoding="utf-8")
            stages.append({"id": stage_id, "name_ar": "مرحلة", "authority": "source owner", "acceptance": "staging proof", "source_paths": [path], "e3_state": "NOT_RUN", "receipt": None})
        self.plan = {"schema": _gate.SCHEMA, "program_id": "TEST", "baseline_commit": "a" * 40,
                     "production_mutations_allowed": False,
                     "promotion_policy": "independent_approval_required", "stages": stages}

    def validate(self):
        return _gate.validate(self.plan, self.root)

    def test_source_review_is_valid_but_not_e3_proof(self):
        result = self.validate()
        self.assertTrue(result["manifest_valid"])
        self.assertFalse(result["complete_e3"])
        self.assertFalse(result["e3_review_candidate"])

    def test_missing_source_is_rejected(self):
        (self.root / self.plan["stages"][0]["source_paths"][0]).unlink()
        self.assertIn("missing_or_escaping_file", str(self.validate()["errors"]))

    def test_duplicate_stage_id_is_rejected(self):
        self.plan["stages"][3]["id"] = self.plan["stages"][2]["id"]
        self.assertIn("stages_missing_reordered_or_duplicated", self.validate()["errors"])

    def test_unsupported_proof_state_is_rejected(self):
        self.plan["stages"][0]["e3_state"] = "PRODUCTION_PROVEN"
        self.assertIn("invalid_e3_state", str(self.validate()["errors"]))

    def test_not_run_cannot_have_receipt(self):
        self.plan["stages"][0]["receipt"] = {}
        self.assertIn("not_run_has_receipt", str(self.validate()["errors"]))

    def test_evidence_submission_needs_actual_matching_bytes(self):
        stage = self.plan["stages"][0]
        stage["e3_state"] = "EVIDENCE_SUBMITTED"
        evidence = self.root / "certification/evidence/data_decision_outcome/one.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text('{"mock_run": true}', encoding="utf-8")
        stage["receipt"] = {"result": "PASS", "environment": "staging", "source_commit": "b"*40,
                            "artifact_path": str(evidence.relative_to(self.root)),
                            "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
        self.assertTrue(self.validate()["manifest_valid"])
        evidence.write_text('{"mock_run": false}', encoding="utf-8")
        self.assertIn("receipt_digest_mismatch", str(self.validate()["errors"]))

    def test_receipt_path_cannot_escape_checkout(self):
        stage = self.plan["stages"][0]
        stage["e3_state"] = "EVIDENCE_SUBMITTED"
        stage["receipt"] = {"result": "PASS", "environment": "ci", "source_commit": "b"*40,
                            "artifact_path": "../other.json", "sha256": "a"*64}
        self.assertIn("path_escape_rejected", str(self.validate()["errors"]))

    def test_unsafe_production_policy_is_rejected(self):
        self.plan["production_mutations_allowed"] = True
        self.assertIn("production_mutations_must_be_disabled", self.validate()["errors"])

    def test_all_submitted_is_review_candidate_not_certification(self):
        for stage in self.plan["stages"]:
            evidence = self.root / f"certification/evidence/data_decision_outcome/{stage['id']}.txt"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("synthetic", encoding="utf-8")
            stage["e3_state"] = "EVIDENCE_SUBMITTED"
            stage["receipt"] = {"result": "PASS", "environment": "ci", "source_commit": "b"*40,
                                "artifact_path": str(evidence.relative_to(self.root)),
                                "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
        result = self.validate()
        self.assertTrue(result["manifest_valid"])
        self.assertTrue(result["e3_review_candidate"])
        self.assertFalse(result["complete_e3"])


    def test_manifest_list_root_returns_structured_failure(self):
        candidate = self.root / "root-array.json"
        candidate.write_text("[]", encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = _gate.main(["--root", str(self.root), "--manifest", str(candidate)])
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(parsed["manifest_valid"])
        self.assertIn("manifest_root_not_object", parsed["errors"])

    def test_unhashable_state_and_environment_fail_structured(self):
        self.plan["stages"][0]["e3_state"] = ["EVIDENCE_SUBMITTED"]
        self.assertIn("invalid_e3_state", str(self.validate()["errors"]))
        self.plan["stages"][0]["e3_state"] = "EVIDENCE_SUBMITTED"
        self.plan["stages"][0]["receipt"] = {
            "result": "PASS", "environment": ["staging"], "source_commit": "b" * 40,
            "artifact_path": "certification/evidence/data_decision_outcome/missing.json",
            "sha256": "a" * 64,
        }
        self.assertIn("invalid_environment", str(self.validate()["errors"]))


if __name__ == "__main__":
    unittest.main()

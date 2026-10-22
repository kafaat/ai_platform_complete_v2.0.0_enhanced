"""Regression proof for Railway staging connectivity without side effects."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import railway_staging_connection_preflight as p  # noqa: E402

TEST_SHA = "d23b320ae6c437273a8c8a6a1ba9fc5f111b1e1c"


class RailwayPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.status = {
            "project": {"id": p.PROJECT_ID, "name": "sahool-staging"},
            "environment": {"id": p.STAGING_ID, "name": "staging"},
            "services": [{"status": "CRASHED"}],
        }

    def test_success_does_not_claim_live_acceptance(self) -> None:
        result = p.validate_status(self.status, TEST_SHA)
        self.assertEqual(result["verdict"], "CONNECTION_ONLY_PASS")
        for flag in (
            "deployment_performed",
            "migration_performed",
            "database_access_verified",
            "runtime_verified",
            "production_certified",
        ):
            self.assertFalse(result[flag], flag)

    def test_accepts_consistent_flat_ids(self) -> None:
        self.status["projectId"] = p.PROJECT_ID
        self.status["environmentId"] = p.STAGING_ID
        self.assertEqual(p.validate_status(self.status, TEST_SHA)["scope"], "staging")

    def test_rejects_missing_id(self) -> None:
        self.status.pop("project")
        with self.assertRaisesRegex(p.PreflightError, "MISSING_PROJECTID"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_conflicting_ids(self) -> None:
        self.status["environmentId"] = p.PRODUCTION_ID
        with self.assertRaisesRegex(p.PreflightError, "CONFLICTING_ENVIRONMENTID"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_production_environment(self) -> None:
        self.status["environment"]["id"] = p.PRODUCTION_ID
        with self.assertRaisesRegex(p.PreflightError, "ENVIRONMENT_ID_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_wrong_environment_name(self) -> None:
        self.status["environment"]["name"] = "production"
        with self.assertRaisesRegex(p.PreflightError, "ENVIRONMENT_NAME_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_wrong_project(self) -> None:
        self.status["project"]["id"] = "00000000-0000-4000-8000-000000000000"
        with self.assertRaisesRegex(p.PreflightError, "PROJECT_ID_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_bad_sha(self) -> None:
        with self.assertRaisesRegex(p.PreflightError, "INVALID_SOURCE_SHA"):
            p.validate_status(self.status, "main")

    def test_rejects_error_payload(self) -> None:
        self.status["errors"] = ["secret must never be printed"]
        with self.assertRaisesRegex(p.PreflightError, "STATUS_HAS_ERROR"):
            p.validate_status(self.status, TEST_SHA)

    def test_receipt_never_includes_cli_secrets(self) -> None:
        self.status["variables"] = {"DATABASE_URL": "must_not_leak"}
        receipt = p.validate_status(self.status, TEST_SHA)
        self.assertNotIn("must_not_leak", json.dumps(receipt))
        self.assertNotIn("variables", json.dumps(receipt))

    def test_workflow_has_no_railway_write_step(self) -> None:
        wf = (
            ROOT / ".github" / "workflows" / "railway-staging-connection-preflight.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", wf)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", wf)
        self.assertIn("secrets.SAHOOL_RAILWAY_STAGING_PROJECT_TOKEN", wf)
        self.assertIn("refs/heads/main", wf)
        self.assertIn("expected_sha", wf)
        self.assertIn("railway status --json", wf)
        for forbidden in (
            "railway up",
            "railway redeploy",
            "railway ssh",
            "railway run",
            "railway variable set",
            "railway environment edit",
        ):
            self.assertNotIn(forbidden, wf.lower())


if __name__ == "__main__":
    unittest.main()

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
        # Railway CLI v5.63.1 serializes ProjectProject directly as JSON.
        self.status = {
            "id": p.PROJECT_ID,
            "name": "sahool-staging",
            "environments": {
                "edges": [
                    {
                        "node": {
                            "id": p.STAGING_ID,
                            "name": "staging",
                            "canAccess": True,
                        }
                    }
                ]
            },
            "services": {"edges": [{"node": {"status": "CRASHED"}}]},
        }

    def test_real_cli_shape_without_runtime_claims(self) -> None:
        result = p.validate_status(self.status, TEST_SHA)
        self.assertEqual(result["verdict"], "CONNECTION_ONLY_PASS")
        self.assertEqual(result["environment_id"], p.STAGING_ID)
        for flag in (
            "deployment_performed",
            "migration_performed",
            "database_access_verified",
            "runtime_verified",
            "production_certified",
        ):
            self.assertFalse(result[flag], flag)

    def test_rejects_legacy_wrapper_instead_of_real_cli_json(self) -> None:
        self.status = {
            "project": {"id": p.PROJECT_ID},
            "environment": {"id": p.STAGING_ID, "name": "staging"},
        }
        with self.assertRaisesRegex(p.PreflightError, "PROJECT_ID_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_missing_project_id(self) -> None:
        self.status.pop("id")
        with self.assertRaisesRegex(p.PreflightError, "PROJECT_ID_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_missing_environments(self) -> None:
        self.status.pop("environments")
        with self.assertRaisesRegex(p.PreflightError, "MISSING_ENVIRONMENTS"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_empty_environment_edges(self) -> None:
        self.status["environments"]["edges"] = []
        with self.assertRaisesRegex(p.PreflightError, "ENVIRONMENT_SCOPE_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_unscoped_multiple_environments(self) -> None:
        self.status["environments"]["edges"].append(
            {"node": {"id": p.PRODUCTION_ID, "name": "production"}}
        )
        with self.assertRaisesRegex(p.PreflightError, "ENVIRONMENT_SCOPE_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_missing_edge_node(self) -> None:
        self.status["environments"]["edges"] = [{}]
        with self.assertRaisesRegex(p.PreflightError, "INVALID_ENVIRONMENT_SHAPE"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_production_environment(self) -> None:
        self.status["environments"]["edges"][0]["node"]["id"] = p.PRODUCTION_ID
        with self.assertRaisesRegex(p.PreflightError, "ENVIRONMENT_ID_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_wrong_environment_name(self) -> None:
        self.status["environments"]["edges"][0]["node"]["name"] = "production"
        with self.assertRaisesRegex(p.PreflightError, "ENVIRONMENT_NAME_MISMATCH"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_staging_inaccessible(self) -> None:
        self.status["environments"]["edges"][0]["node"]["canAccess"] = False
        with self.assertRaisesRegex(p.PreflightError, "STAGING_ACCESS_DENIED"):
            p.validate_status(self.status, TEST_SHA)

    def test_rejects_wrong_project(self) -> None:
        self.status["id"] = "00000000-0000-4000-8000-000000000000"
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

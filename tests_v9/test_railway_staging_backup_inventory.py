"""Offline proof that backup inventory never acts on or certifies Railway data."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import railway_staging_backup_inventory as bi  # noqa: E402

SHA = "a" * 40
INSTANCE_ID = "b5168cf7-29ac-4ba8-b2b1-909090909090"


def status_fixture() -> dict:
    return {
        "id": bi.PROJECT_ID,
        "environments": {
            "edges": [
                {
                    "node": {
                        "id": bi.STAGING_ID,
                        "name": "staging",
                        "canAccess": True,
                        "volumeInstances": {
                            "edges": [
                                {
                                    "node": {
                                        "id": INSTANCE_ID,
                                        "environmentId": bi.STAGING_ID,
                                        "serviceId": bi.POSTGRES_SERVICE_ID,
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        },
    }


def volume_fixture() -> dict:
    return {
        "id": INSTANCE_ID,
        "mountPath": bi.POSTGRES_MOUNT,
        "volume": {"id": bi.POSTGRES_VOLUME_ID, "name": "database secret name"},
        "serviceInstance": {"serviceName": "sahool-postgres"},
    }


def scope_fixture() -> dict:
    return {"projectId": bi.PROJECT_ID, "environmentId": bi.STAGING_ID}


def backups_fixture() -> list[dict]:
    return [
        {
            "id": "private-backup-identifier-abc",
            "createdAt": "2026-11-07T10:00:00Z",
            "expiresAt": "2026-11-14T10:00:00Z",
            "usedMB": 17,
            "referencedMB": 22,
            "name": "private-backup-name-abc",
        }
    ]


class BackupInventoryTests(unittest.TestCase):
    def make_receipt(self, **changes):
        args = {
            "status": status_fixture(),
            "source_sha": SHA,
            "scope": scope_fixture(),
            "volume": volume_fixture(),
            "backups": backups_fixture(),
            "observed_at": datetime(2026, 11, 8, tzinfo=UTC),
        }
        args.update(changes)
        return bi.inventory_receipt(**args)

    def test_positive_inventory_is_not_restore_proof(self):
        receipt = self.make_receipt()
        self.assertEqual(receipt["backup_count"], 1)
        self.assertEqual(receipt["unexpired_backup_count"], 1)
        self.assertEqual(receipt["verdict"], "BACKUP_LIST_PRESENT_NOT_RESTORE_PROVEN")
        self.assertTrue(receipt["project_token_scope_verified"])
        for name in (
            "backup_restored",
            "database_access_verified",
            "e3_certified",
            "production_certified",
        ):
            self.assertIs(receipt[name], False)
        self.assertTrue(receipt["read_only"])

    def test_no_backups_stays_unproven(self):
        receipt = self.make_receipt(backups=[])
        self.assertEqual(receipt["backup_count"], 0)
        self.assertEqual(receipt["verdict"], "NO_ACTIVE_BACKUP_PROVEN")
        self.assertFalse(receipt["backup_restored"])

    def test_expired_backup_does_not_count_as_active(self):
        backup = backups_fixture()
        backup[0]["expiresAt"] = "2026-11-07T20:00:00Z"
        receipt = self.make_receipt(backups=backup)
        self.assertEqual(receipt["unexpired_backup_count"], 0)

    def test_raw_backup_names_ids_and_scope_secret_are_not_in_receipt(self):
        receipt = json.dumps(self.make_receipt(), sort_keys=True)
        self.assertNotIn("private-backup-name", receipt)
        self.assertNotIn("private-backup-identifier", receipt)
        self.assertNotIn("database secret name", receipt)
        self.assertNotIn(INSTANCE_ID, receipt)

    def test_rejects_production_project_token_even_with_staging_status(self):
        wrong = scope_fixture()
        wrong["environmentId"] = bi.connection.PRODUCTION_ID
        with self.assertRaisesRegex(bi.InventoryError, "PROJECT_TOKEN_ENVIRONMENT_MISMATCH"):
            self.make_receipt(scope=wrong)

    def test_rejects_wrong_project_token_project(self):
        wrong = scope_fixture()
        wrong["projectId"] = "not-sahool"
        with self.assertRaisesRegex(bi.InventoryError, "PROJECT_TOKEN_PROJECT_MISMATCH"):
            self.make_receipt(scope=wrong)

    def test_rejects_production_volume_instance(self):
        status = status_fixture()
        instance = status["environments"]["edges"][0]["node"]["volumeInstances"]["edges"][0]["node"]
        instance["environmentId"] = bi.connection.PRODUCTION_ID
        with self.assertRaisesRegex(bi.InventoryError, "POSTGRES_INSTANCE_ENVIRONMENT"):
            self.make_receipt(status=status)

    def test_rejects_duplicate_postgres_instances(self):
        status = status_fixture()
        edges = status["environments"]["edges"][0]["node"]["volumeInstances"]["edges"]
        edges.append(edges[0])
        with self.assertRaisesRegex(bi.InventoryError, "POSTGRES_INSTANCE_NOT_UNIQUE"):
            self.make_receipt(status=status)

    def test_rejects_missing_volume_instances(self):
        status = status_fixture()
        del status["environments"]["edges"][0]["node"]["volumeInstances"]
        with self.assertRaisesRegex(bi.InventoryError, "VOLUME_INSTANCES_UNAVAILABLE"):
            self.make_receipt(status=status)

    def test_rejects_wrong_service_volume_and_mount(self):
        for key, replacement, error in (
            ("mountPath", "/data", "POSTGRES_MOUNT_MISMATCH"),
            ("volume", {"id": "other"}, "POSTGRES_LOGICAL_VOLUME_MISMATCH"),
            ("serviceInstance", {"serviceName": "other"}, "POSTGRES_SERVICE_MISMATCH"),
        ):
            volume = volume_fixture()
            volume[key] = replacement
            with self.subTest(key=key), self.assertRaisesRegex(bi.InventoryError, error):
                self.make_receipt(volume=volume)

    def test_rejects_wrong_instance_identity(self):
        volume = volume_fixture()
        volume["id"] = "00000000-0000-4000-8000-000000000000"
        with self.assertRaisesRegex(bi.InventoryError, "VOLUME_IDENTITY_MISMATCH"):
            self.make_receipt(volume=volume)

    def test_rejects_duplicate_backup_and_invalid_dates(self):
        b = backups_fixture()
        with self.assertRaisesRegex(bi.InventoryError, "BACKUP_ID_DUPLICATE_OR_EMPTY"):
            self.make_receipt(backups=b + b)
        b[0]["expiresAt"] = "bad date"
        with self.assertRaisesRegex(bi.InventoryError, "BACKUP_TIMESTAMP_INVALID"):
            self.make_receipt(backups=b)

    def test_rejects_negative_or_boolean_backup_sizes(self):
        b = backups_fixture()
        b[0]["usedMB"] = -1
        with self.assertRaisesRegex(bi.InventoryError, "BACKUP_SIZE_INVALID"):
            self.make_receipt(backups=b)
        b[0]["usedMB"] = True
        with self.assertRaisesRegex(bi.InventoryError, "BACKUP_SIZE_INVALID"):
            self.make_receipt(backups=b)

    def test_rejects_http_200_with_graphql_errors(self):
        raw = {"data": {"volumeInstanceBackupList": backups_fixture()}, "errors": []}
        self.assertEqual(bi.checked_data(raw, "volumeInstanceBackupList"), backups_fixture())
        raw["errors"] = [{"message": "private secret leaked"}]
        with self.assertRaisesRegex(bi.InventoryError, "GRAPHQL_ERRORS_OR_INVALID_RESPONSE"):
            bi.checked_data(raw, "volumeInstanceBackupList")

    def test_graphql_operations_are_query_only_and_fixed_endpoint(self):
        self.assertEqual(bi.ENDPOINT, "https://backboard.railway.com/graphql/v2")
        self.assertEqual(len(bi.QUERIES), 3)
        for query in bi.QUERIES:
            self.assertRegex(query.lstrip(), r"^query\b")
            self.assertNotRegex(query.lower(), r"\bmutation\b")
        with mock.patch.object(bi.urllib.request, "urlopen") as urlopen:
            with self.assertRaisesRegex(bi.InventoryError, "NON_READ_ONLY_OPERATION_REJECTED"):
                bi._post_query("secret", "mutation { volumeDelete }", {})
            urlopen.assert_not_called()

    def test_cli_without_token_fails_closed_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            status = Path(root) / "status.json"
            evidence = Path(root) / "evidence.json"
            status.write_text(json.dumps(status_fixture()), encoding="utf-8")
            with (
                mock.patch.dict(os.environ, {"RAILWAY_STAGING_PROJECT_TOKEN": ""}),
                mock.patch.object(bi.urllib.request, "urlopen") as api,
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "backup_inventory.py",
                        "--status-json",
                        str(status),
                        "--source-sha",
                        SHA,
                        "--evidence",
                        str(evidence),
                    ],
                ),
            ):
                self.assertEqual(bi.main(), 1)
            self.assertFalse(evidence.exists())
            api.assert_not_called()

    def test_capability_scanners_exclude_proof_witnesses(self):
        for path in (
            "scripts/ci/capability_mapping_engine.py",
            "scripts/ci/capability_linker.py",
        ):
            source = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn('"scripts/ci/railway_staging_backup_inventory.py"', source)
            self.assertIn('"tests_v9/test_railway_staging_backup_inventory.py"', source)

    def test_existing_connection_workflow_stays_manual_and_has_no_mutations(self):
        wf = (ROOT / ".github/workflows/railway-staging-connection-preflight.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", wf)
        self.assertIn("refs/heads/main", wf)
        self.assertIn("backup_inventory:", wf)
        self.assertIn("scripts/ci/railway_staging_backup_inventory.py", wf)
        self.assertNotIn("volumeInstanceBackupRestore", wf)
        self.assertNotIn("volumeInstanceBackupCreate", wf)
        self.assertNotIn("RAILWAY_API_TOKEN: ", wf)


if __name__ == "__main__":
    unittest.main()

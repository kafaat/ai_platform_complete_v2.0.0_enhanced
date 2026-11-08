#!/usr/bin/env python3
"""Read-only staging PostgreSQL volume-backup inventory; never restore or certify.

This is an OPT-IN supplement to the existing staging connection proof. It uses
the same environment-scoped project token and emits only allowlisted metadata.
A listed backup is NOT a successful restore drill or E3 acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import railway_staging_connection_preflight as connection

PROJECT_ID = connection.PROJECT_ID
STAGING_ID = connection.STAGING_ID
POSTGRES_SERVICE_ID = "ab01995b-761f-4f8b-9d0b-e9a62a0876bd"
POSTGRES_VOLUME_ID = "d88ef422-c299-4ed9-b31d-1dc668a1d35b"
POSTGRES_MOUNT = "/var/lib/postgresql/data"
ENDPOINT = "https://backboard.railway.com/graphql/v2"
SCHEMA = "sahool.ddo_staging_backup_inventory/v1"
MAX_RESPONSE = 512_000

TOKEN_SCOPE_QUERY = """
query StagingProjectToken {
  projectToken { projectId environmentId }
}
"""
VOLUME_QUERY = """
query DdoStagingVolumeInstance($id: String!) {
  volumeInstance(id: $id) {
    id
    mountPath
    volume { id name }
    serviceInstance { serviceName }
  }
}
"""
BACKUPS_QUERY = """
query DdoStagingVolumeBackups($volumeInstanceId: String!) {
  volumeInstanceBackupList(volumeInstanceId: $volumeInstanceId) {
    id createdAt expiresAt usedMB referencedMB
  }
}
"""
QUERIES = frozenset((TOKEN_SCOPE_QUERY, VOLUME_QUERY, BACKUPS_QUERY))


class InventoryError(ValueError):
    """Error messages must be fixed codes, never untrusted API/CLI text."""


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise InventoryError("VOLUME_INSTANCE_ID_INVALID")
    try:
        return str(UUID(value))
    except ValueError:
        raise InventoryError("VOLUME_INSTANCE_ID_INVALID") from None


def select_instance(status: Any, source_sha: str) -> str:
    """Reuse the existing strict project/staging scope verifier."""
    try:
        connection.validate_status(status, source_sha)
    except connection.PreflightError:
        raise InventoryError("STAGING_CONNECTION_SCOPE_INVALID") from None

    node = status["environments"]["edges"][0]["node"]
    volumes = node.get("volumeInstances")
    if not isinstance(volumes, dict) or not isinstance(volumes.get("edges"), list):
        raise InventoryError("VOLUME_INSTANCES_UNAVAILABLE")
    edges = volumes["edges"]
    candidates: list[str] = []
    for edge in edges:
        item = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(item, dict):
            raise InventoryError("VOLUME_INSTANCE_SHAPE_INVALID")
        if item.get("serviceId") != POSTGRES_SERVICE_ID:
            continue
        if item.get("environmentId") != STAGING_ID:
            raise InventoryError("POSTGRES_INSTANCE_ENVIRONMENT_MISMATCH")
        candidates.append(_uuid(item.get("id")))
    if len(candidates) != 1 or len(set(candidates)) != 1:
        raise InventoryError("POSTGRES_INSTANCE_NOT_UNIQUE")
    return candidates[0]


def checked_data(payload: Any, field: str) -> Any:
    if not isinstance(payload, dict) or payload.get("errors"):
        raise InventoryError("GRAPHQL_ERRORS_OR_INVALID_RESPONSE")
    data = payload.get("data")
    if not isinstance(data, dict) or field not in data or data[field] is None:
        raise InventoryError("GRAPHQL_DATA_MISSING")
    return data[field]


def _post_query(token: str, query: str, variables: dict[str, str]) -> dict[str, Any]:
    if query not in QUERIES or re.search(r"\bmutation\b", query, re.IGNORECASE):
        raise InventoryError("NON_READ_ONLY_OPERATION_REJECTED")
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Project-Access-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise InventoryError("RAILWAY_QUERY_UNAVAILABLE") from None
    if len(raw) > MAX_RESPONSE:
        raise InventoryError("RAILWAY_RESPONSE_TOO_LARGE")
    try:
        result = json.loads(raw)
    except (UnicodeError, ValueError):
        raise InventoryError("RAILWAY_RESPONSE_INVALID_JSON") from None
    if not isinstance(result, dict):
        raise InventoryError("RAILWAY_RESPONSE_INVALID_SHAPE")
    return result


def _timestamp(raw: Any, *, optional: bool = False) -> datetime | None:
    if optional and raw is None:
        return None
    if not isinstance(raw, str):
        raise InventoryError("BACKUP_TIMESTAMP_INVALID")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise InventoryError("BACKUP_TIMESTAMP_INVALID") from None
    if value.tzinfo is None:
        raise InventoryError("BACKUP_TIMESTAMP_MISSING_ZONE")
    return value.astimezone(UTC)


def inventory_receipt(
    *,
    status: Any,
    source_sha: str,
    scope: Any,
    volume: Any,
    backups: Any,
    observed_at: datetime,
) -> dict[str, Any]:
    instance_id = select_instance(status, source_sha)
    if not isinstance(scope, dict) or scope.get("projectId") != PROJECT_ID:
        raise InventoryError("PROJECT_TOKEN_PROJECT_MISMATCH")
    if scope.get("environmentId") != STAGING_ID:
        raise InventoryError("PROJECT_TOKEN_ENVIRONMENT_MISMATCH")
    if not isinstance(volume, dict) or _uuid(volume.get("id")) != instance_id:
        raise InventoryError("VOLUME_IDENTITY_MISMATCH")
    metadata = volume.get("volume")
    service = volume.get("serviceInstance")
    if not isinstance(metadata, dict) or metadata.get("id") != POSTGRES_VOLUME_ID:
        raise InventoryError("POSTGRES_LOGICAL_VOLUME_MISMATCH")
    if not isinstance(service, dict) or service.get("serviceName") != "sahool-postgres":
        raise InventoryError("POSTGRES_SERVICE_MISMATCH")
    if volume.get("mountPath") != POSTGRES_MOUNT:
        raise InventoryError("POSTGRES_MOUNT_MISMATCH")
    if not isinstance(backups, list):
        raise InventoryError("BACKUP_LIST_INVALID")
    ids: set[str] = set()
    sanitized_rows: list[dict[str, Any]] = []
    for backup in backups:
        if not isinstance(backup, dict) or not isinstance(backup.get("id"), str):
            raise InventoryError("BACKUP_ENTRY_INVALID")
        bid = backup["id"]
        if not bid or bid in ids:
            raise InventoryError("BACKUP_ID_DUPLICATE_OR_EMPTY")
        ids.add(bid)
        created = _timestamp(backup.get("createdAt"))
        expires = _timestamp(backup.get("expiresAt"), optional=True)
        if expires is not None and expires < created:
            raise InventoryError("BACKUP_EXPIRY_BEFORE_CREATION")
        for key in ("usedMB", "referencedMB"):
            value = backup.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise InventoryError("BACKUP_SIZE_INVALID")
        sanitized_rows.append(
            {"id": bid, "created_at": created.isoformat(), "expires_at": expires.isoformat() if expires else None}
        )
    canonical = json.dumps(
        sorted(sanitized_rows, key=lambda row: row["id"]), sort_keys=True
    ).encode("utf-8")
    active = sum(
        1 for row in sanitized_rows
        if row["expires_at"] is None or datetime.fromisoformat(row["expires_at"]) > observed_at
    )
    latest = max((row["created_at"] for row in sanitized_rows), default=None)
    return {
        "schema": SCHEMA,
        "verdict": "BACKUP_LIST_PRESENT_NOT_RESTORE_PROVEN" if active else "NO_ACTIVE_BACKUP_PROVEN",
        "project_id": PROJECT_ID,
        "environment_id": STAGING_ID,
        "service": "sahool-postgres",
        "source_sha": source_sha,
        "volume_instance_sha256": hashlib.sha256(instance_id.encode("ascii")).hexdigest(),
        "backup_inventory_sha256": hashlib.sha256(canonical).hexdigest(),
        "backup_count": len(backups),
        "unexpired_backup_count": active,
        "latest_backup_created_at": latest,
        "observed_at_utc": observed_at.isoformat(),
        "project_token_scope_verified": True,
        "read_only": True,
        "backup_restored": False,
        "database_access_verified": False,
        "e3_certified": False,
        "production_certified": False,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status-json", type=Path, required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    args = ap.parse_args(argv)
    token = os.getenv("RAILWAY_STAGING_PROJECT_TOKEN", "")
    try:
        if not token:
            raise InventoryError("STAGING_PROJECT_TOKEN_MISSING")
        if args.status_json.stat().st_size > connection.MAX_STATUS_BYTES:
            raise InventoryError("STATUS_FILE_TOO_LARGE")
        try:
            status = json.loads(args.status_json.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError):
            raise InventoryError("STATUS_JSON_INVALID") from None
        instance = select_instance(status, args.source_sha)
        scope = checked_data(_post_query(token, TOKEN_SCOPE_QUERY, {}), "projectToken")
        volume = checked_data(
            _post_query(token, VOLUME_QUERY, {"id": instance}), "volumeInstance"
        )
        backups = checked_data(
            _post_query(token, BACKUPS_QUERY, {"volumeInstanceId": instance}),
            "volumeInstanceBackupList",
        )
        receipt = inventory_receipt(
            status=status,
            source_sha=args.source_sha,
            scope=scope,
            volume=volume,
            backups=backups,
            observed_at=datetime.now(UTC),
        )
        args.evidence.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    except (InventoryError, OSError) as exc:
        code = str(exc) if isinstance(exc, InventoryError) else "LOCAL_IO_ERROR"
        print("::error::" + code, file=sys.stderr)
        return 1
    print(receipt["verdict"] + ": inventory-only; no backup restore or database access")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

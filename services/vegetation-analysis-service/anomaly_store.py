"""Durable local anomaly lifecycle store for RS-6.

SQLite is used deliberately to provide atomic state transitions without adding a
cross-service database dependency. Production deployments must mount the path on
persistent storage; the store owns only vegetation-analysis anomaly state.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ALLOWED_TRANSITIONS = {
    "detected": {"triaged", "verification_requested", "resolved"},
    "triaged": {"verification_requested", "resolved"},
    "verification_requested": {"confirmed", "rejected", "inconclusive"},
    "inconclusive": {"verification_requested", "resolved"},
    "confirmed": {"diagnosis_proposed", "resolved"},
    "diagnosis_proposed": {"decision_referred", "resolved"},
    "decision_referred": {"resolved"},
    "rejected": {"resolved"},
    "resolved": set(),
}


class InvalidTransition(ValueError):
    pass


class AnomalyNotFound(KeyError):
    pass


class AnomalyStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.getenv("VEGETATION_ANOMALY_DB_PATH", "/tmp/sahool-anomalies.db")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS signal_anomalies (
                    anomaly_ref TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    field_id TEXT NOT NULL,
                    season_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    task_ref TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signal_anomalies_field ON signal_anomalies(tenant_id, field_id, season_id, status)"
            )

    def upsert_detected(self, payload: dict[str, Any]) -> dict[str, Any]:
        ref = str(payload["anomaly_ref"])
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT OR IGNORE INTO signal_anomalies
                   (anomaly_ref, tenant_id, field_id, season_id, status, version, payload_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'detected', 1, ?, ?, ?)""",
                (
                    ref,
                    str(payload["tenant_id"]),
                    str(payload["field_id"]),
                    str(payload["season_id"]),
                    json.dumps(payload, sort_keys=True, default=str),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM signal_anomalies WHERE anomaly_ref = ?", (ref,)
            ).fetchone()
            conn.commit()
            return self._row(row)

    def get(self, anomaly_ref: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM signal_anomalies WHERE anomaly_ref = ?", (anomaly_ref,)
            ).fetchone()
        if not row:
            raise AnomalyNotFound(anomaly_ref)
        return self._row(row)

    def list(self, tenant_id: str, field_id: str, season_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM signal_anomalies
                   WHERE tenant_id = ? AND field_id = ? AND season_id = ?
                   ORDER BY created_at DESC""",
                (tenant_id, field_id, season_id),
            ).fetchall()
        return [self._row(row) for row in rows]

    def transition(
        self,
        anomaly_ref: str,
        new_status: str,
        *,
        expected_version: int,
        patch: dict[str, Any] | None = None,
        task_ref: str | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM signal_anomalies WHERE anomaly_ref = ?", (anomaly_ref,)
            ).fetchone()
            if not row:
                raise AnomalyNotFound(anomaly_ref)
            current = str(row["status"])
            if int(row["version"]) != expected_version:
                raise InvalidTransition("aggregate_version_conflict")
            if new_status not in _ALLOWED_TRANSITIONS.get(current, set()):
                raise InvalidTransition(f"invalid_transition:{current}->{new_status}")
            payload = json.loads(row["payload_json"])
            payload.update(patch or {})
            payload["status"] = new_status
            payload["updated_at"] = datetime.now(UTC).isoformat()
            version = expected_version + 1
            cursor = conn.execute(
                """UPDATE signal_anomalies
                   SET status = ?, version = ?, task_ref = COALESCE(?, task_ref), payload_json = ?, updated_at = ?
                   WHERE anomaly_ref = ? AND version = ?""",
                (
                    new_status,
                    version,
                    task_ref,
                    json.dumps(payload, sort_keys=True, default=str),
                    payload["updated_at"],
                    anomaly_ref,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                raise InvalidTransition("aggregate_version_conflict")
            updated = conn.execute(
                "SELECT * FROM signal_anomalies WHERE anomaly_ref = ?", (anomaly_ref,)
            ).fetchone()
            conn.commit()
            return self._row(updated)

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "anomaly_ref": row["anomaly_ref"],
            "tenant_id": row["tenant_id"],
            "field_id": row["field_id"],
            "season_id": row["season_id"],
            "status": row["status"],
            "aggregate_version": int(row["version"]),
            "task_ref": row["task_ref"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

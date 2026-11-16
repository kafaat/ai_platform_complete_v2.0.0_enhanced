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
import time
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


def _pending_reservation(payload: dict) -> dict | None:
    reservation = payload.get("verification_reservation")
    if isinstance(reservation, dict) and reservation.get("state") == "pending":
        return reservation
    return None


def validate_transition(current: str, new_status: str, payload: dict, patch: dict | None) -> None:
    """Allow one metadata-only recovery of a legacy confirmed aggregate.

    The trusted task callback supplies the original metadata; no status or
    evidence reference can be replaced during recovery. Both stores use this.

    While a ground-verification reservation is pending (the field task is being
    dispatched), no generic transition may run: only the reservation's own attach
    or release operation may move the aggregate. Otherwise a concurrent resolve or
    a verification result could close the anomaly under the dispatch and strand
    the field task (SCOUTING-ANOMALY-VERIFY-RACE-ORPHAN-TASK-01).
    """
    if _pending_reservation(payload) is not None:
        raise InvalidTransition("verification_reservation_pending")
    if current == new_status == "confirmed":
        patch = patch or {}
        evidence = patch.get("verification_evidence") or []
        if (
            not payload.get("verification_evidence")
            and evidence
            and set(patch) == {"verification_evidence", "verification_metadata_recovered_at"}
            and {e.get("evidence_ref") for e in evidence}
            == set(payload.get("verification_evidence_refs") or [])
        ):
            return
    if new_status not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"invalid_transition:{current}->{new_status}")


# --- ground-verification reservation (SCOUTING-ANOMALY-VERIFY-RACE-ORPHAN-TASK-01) ---------
#
# Each plan takes the locked row's status, payload and task_ref and returns the new
# (status, payload, task_ref). Both stores run them inside their versioned, row-locked
# mutation, so the reservation is taken against the expected version atomically.


def plan_reservation(
    current: str,
    payload: dict,
    task_ref: str | None,
    *,
    idempotency_key: str,
    reserved_from_version: int,
) -> tuple[str, dict, str | None]:
    """Reserve verification before any field task is dispatched.

    The aggregate moves to ``verification_requested`` with a pending reservation and no
    task yet; the prior status is kept so a dispatch that created no task can restore it.
    """
    if not idempotency_key:
        raise InvalidTransition("verification_reservation_key_required")
    validate_transition(current, "verification_requested", payload, None)
    if task_ref:
        raise InvalidTransition("reverification_not_supported:anomaly_already_has_task")
    now = datetime.now(UTC).isoformat()
    payload["verification_reservation"] = {
        "state": "pending",
        "prior_status": current,
        "idempotency_key": idempotency_key,
        "reserved_from_version": reserved_from_version,
        "reserved_at": now,
    }
    payload.pop("verification_reservation_released", None)
    return "verification_requested", payload, None


def _bound_reservation(current: str, payload: dict, idempotency_key: str) -> dict:
    reservation = _pending_reservation(payload)
    if current != "verification_requested" or reservation is None:
        raise InvalidTransition("verification_reservation_missing")
    if reservation.get("idempotency_key") != idempotency_key:
        raise InvalidTransition("verification_reservation_key_mismatch")
    return reservation


def plan_attach(
    current: str,
    payload: dict,
    task_ref: str | None,
    *,
    idempotency_key: str,
    new_task_ref: str,
) -> tuple[str, dict, str | None]:
    """Attach the dispatched field task to its pending reservation."""
    if not new_task_ref:
        raise InvalidTransition("verification_task_ref_required")
    reservation = _bound_reservation(current, payload, idempotency_key)
    if task_ref and task_ref != new_task_ref:
        raise InvalidTransition("verification_task_ref_mismatch")
    payload["verification_reservation"] = {
        **reservation,
        "state": "attached",
        "attached_at": datetime.now(UTC).isoformat(),
    }
    payload["task_ref"] = new_task_ref
    return "verification_requested", payload, new_task_ref


def plan_release(
    current: str,
    payload: dict,
    task_ref: str | None,
    *,
    idempotency_key: str,
    reason: str,
) -> tuple[str, dict, str | None]:
    """Give a pending reservation back: the dispatch created no task, so the prior state returns."""
    reservation = _bound_reservation(current, payload, idempotency_key)
    if task_ref:
        raise InvalidTransition("verification_reservation_already_attached")
    prior = str(reservation.get("prior_status") or "")
    if "verification_requested" not in _ALLOWED_TRANSITIONS.get(prior, set()):
        raise InvalidTransition(f"verification_reservation_prior_status_invalid:{prior}")
    payload.pop("verification_reservation", None)
    payload["verification_reservation_released"] = {
        "prior_status": prior,
        "reason": reason,
        "released_at": datetime.now(UTC).isoformat(),
    }
    return prior, payload, None


class AnomalyStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.getenv("VEGETATION_ANOMALY_DB_PATH", "/tmp/sahool-anomalies.db")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        # Two image workers can race while converting a new database to WAL.
        # SQLite may return BUSY immediately for that lock upgrade despite the
        # connection timeout. Retry a fresh connection within one bounded budget.
        deadline = time.monotonic() + 10
        while True:
            conn = sqlite3.connect(
                self.path, timeout=max(0, deadline - time.monotonic()), isolation_level=None
            )
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute("PRAGMA busy_timeout=10000")
                return conn
            except sqlite3.OperationalError as exc:
                conn.close()
                remaining = deadline - time.monotonic()
                if (
                    getattr(exc, "sqlite_errorcode", 0) & 0xFF != sqlite3.SQLITE_BUSY
                    or remaining <= 0
                ):
                    raise
                time.sleep(min(0.05, remaining))
            except BaseException:
                conn.close()
                raise

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

    def get(self, anomaly_ref: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        with self._connect() as conn:
            if tenant_id is None:
                row = conn.execute(
                    "SELECT * FROM signal_anomalies WHERE anomaly_ref = ?", (anomaly_ref,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM signal_anomalies WHERE anomaly_ref = ? AND tenant_id = ?",
                    (anomaly_ref, tenant_id),
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
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        def plan(current: str, payload: dict, _task_ref: str | None):
            validate_transition(current, new_status, payload, patch)
            payload.update(patch or {})
            return new_status, payload, task_ref

        return self._mutate(anomaly_ref, expected_version, tenant_id, plan)

    def reserve_verification(
        self,
        anomaly_ref: str,
        *,
        expected_version: int,
        idempotency_key: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        return self._mutate(
            anomaly_ref,
            expected_version,
            tenant_id,
            lambda current, payload, task_ref: plan_reservation(
                current,
                payload,
                task_ref,
                idempotency_key=idempotency_key,
                reserved_from_version=expected_version,
            ),
        )

    def attach_verification_task(
        self,
        anomaly_ref: str,
        *,
        expected_version: int,
        idempotency_key: str,
        task_ref: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        return self._mutate(
            anomaly_ref,
            expected_version,
            tenant_id,
            lambda current, payload, row_task_ref: plan_attach(
                current,
                payload,
                row_task_ref,
                idempotency_key=idempotency_key,
                new_task_ref=task_ref,
            ),
        )

    def release_verification_reservation(
        self,
        anomaly_ref: str,
        *,
        expected_version: int,
        idempotency_key: str,
        reason: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        return self._mutate(
            anomaly_ref,
            expected_version,
            tenant_id,
            lambda current, payload, task_ref: plan_release(
                current, payload, task_ref, idempotency_key=idempotency_key, reason=reason
            ),
        )

    def _mutate(
        self,
        anomaly_ref: str,
        expected_version: int,
        tenant_id: str | None,
        plan: Any,
    ) -> dict[str, Any]:
        """One versioned, write-locked state change; ``plan`` decides the new state."""
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if tenant_id is None:
                row = conn.execute(
                    "SELECT * FROM signal_anomalies WHERE anomaly_ref = ?", (anomaly_ref,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM signal_anomalies WHERE anomaly_ref = ? AND tenant_id = ?",
                    (anomaly_ref, tenant_id),
                ).fetchone()
            if not row:
                raise AnomalyNotFound(anomaly_ref)
            current = str(row["status"])
            if int(row["version"]) != expected_version:
                raise InvalidTransition("aggregate_version_conflict")
            payload = json.loads(row["payload_json"])
            new_status, payload, task_ref = plan(current, payload, row["task_ref"])
            payload["status"] = new_status
            payload["updated_at"] = datetime.now(UTC).isoformat()
            version = expected_version + 1
            cursor = conn.execute(
                """UPDATE signal_anomalies
                   SET status = ?, version = ?, task_ref = COALESCE(?, task_ref), payload_json = ?, updated_at = ?
                   WHERE anomaly_ref = ? AND version = ?
                     AND (? IS NULL OR tenant_id = ?)""",
                (
                    new_status,
                    version,
                    task_ref,
                    json.dumps(payload, sort_keys=True, default=str),
                    payload["updated_at"],
                    anomaly_ref,
                    expected_version,
                    tenant_id,
                    tenant_id,
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

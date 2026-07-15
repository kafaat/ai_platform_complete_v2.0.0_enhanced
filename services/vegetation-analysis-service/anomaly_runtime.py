"""Process-local wiring for the RS anomaly aggregate store.

The backend is selected by VEGETATION_ANOMALY_STORE:
  * "sqlite"   (default) — the service-local single-replica store; behaviour is
                unchanged from before this switch existed.
  * "postgres" — the durable multi-replica PostgreSQL + FORCE RLS store (v191),
                for horizontal scale. Opt-in until certified on a live database.

Both backends are exposed through one *async* facade so routers can await
uniformly regardless of which is active.
"""

from __future__ import annotations

import inspect
import os
from typing import Any


async def _maybe(value: Any) -> Any:
    """Await async backends; pass through sync ones."""
    return await value if inspect.isawaitable(value) else value


class AnomalyStoreFacade:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    async def upsert_detected(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await _maybe(self._backend.upsert_detected(payload))

    async def get(self, anomaly_ref: str, *, tenant_id: str) -> dict[str, Any]:
        return await _maybe(self._backend.get(anomaly_ref, tenant_id=tenant_id))

    async def list(self, tenant_id: str, field_id: str, season_id: str) -> list[dict[str, Any]]:
        return await _maybe(self._backend.list(tenant_id, field_id, season_id))

    async def transition(
        self,
        anomaly_ref: str,
        new_status: str,
        *,
        expected_version: int,
        patch: dict[str, Any] | None = None,
        task_ref: str | None = None,
        tenant_id: str,
    ) -> dict[str, Any]:
        return await _maybe(
            self._backend.transition(
                anomaly_ref,
                new_status,
                expected_version=expected_version,
                patch=patch,
                task_ref=task_ref,
                tenant_id=tenant_id,
            )
        )


def _make_backend() -> Any:
    backend = os.getenv("VEGETATION_ANOMALY_STORE", "sqlite").strip().lower()
    if backend == "postgres":
        from anomaly_store_pg import PostgresAnomalyStore

        return PostgresAnomalyStore()
    from anomaly_store import AnomalyStore

    return AnomalyStore()


store = AnomalyStoreFacade(_make_backend())

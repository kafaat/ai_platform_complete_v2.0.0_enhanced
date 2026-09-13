"""Durable edge synchronization: one envelope survives timeout and restart."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class CloudSyncService:
    def __init__(self, cloud_url: str, token: str, sync_dir: str = "/data/sync_queue"):
        self.cloud_url = cloud_url.rstrip("/")
        self.token = token
        self.sync_dir = sync_dir
        self.last_sync: datetime | None = None
        Path(sync_dir).mkdir(parents=True, exist_ok=True)

    def queue_size(self) -> int:
        return len(list(Path(self.sync_dir).glob("*.json")))

    def _envelope(self, result_type: str, data: dict, idem_key: str | None = None) -> dict:
        field_id = data.get("field_id")
        device_id = data.get("device_id") or os.getenv("EDGE_DEVICE_ID", "")
        if not isinstance(field_id, str) or not field_id.strip() or len(field_id) > 50:
            raise ValueError("edge_field_id_required")
        if not isinstance(device_id, str) or not device_id.strip() or len(device_id) > 50:
            raise ValueError("edge_device_id_required")
        occurred_at = (
            data.get("occurred_at") or data.get("timestamp") or datetime.now(UTC).isoformat()
        )
        parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("edge_timestamp_timezone_required")
        return {
            "type": result_type,
            "data": data,
            "field_id": field_id,
            "device_id": device_id,
            "idempotency_key": idem_key or uuid.uuid4().hex,
            "occurred_at": parsed.isoformat(),
            "queued_at": datetime.now(UTC).isoformat(),
        }

    def _persist(self, item: dict, path: Path | None = None) -> Path:
        path = path or Path(self.sync_dir) / f"{item['idempotency_key']}.json"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.sync_dir, suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(item, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            descriptor = os.open(self.sync_dir, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    def queue_result(self, result_type: str, data: dict):
        return self._persist(self._envelope(result_type, data))

    def _queue_with_key(self, result_type: str, data: dict, idem_key: str):
        return self._persist(self._envelope(result_type, data, idem_key))

    async def _send(self, client, item: dict) -> None:
        if not self.token:
            raise ValueError("edge_sync_token_required")
        response = await client.post(
            f"{self.cloud_url}/v1/edge/sync",
            json=item,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        response.raise_for_status()
        receipt = response.json()
        if (
            receipt.get("status") not in {"stored", "duplicate_ignored"}
            or receipt.get("idempotency_key") != item["idempotency_key"]
        ):
            raise ValueError("edge_sync_receipt_mismatch")

    async def sync_result(self, result_type: str, data: dict) -> bool:
        item = self._envelope(result_type, data)
        # Persist BEFORE network I/O. A crash after acceptance still leaves the
        # same key and observation timestamp available for idempotent replay.
        path = self._persist(item)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await self._send(client, item)
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.info("Edge result retained for retry: %s", type(exc).__name__)
            return False
        self.last_sync = datetime.now(UTC)
        return True

    async def process_queue(self) -> int:
        synced = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            for path in sorted(Path(self.sync_dir).glob("*.json")):
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                    # Older queue files already contain the observation timestamp
                    # inside data. Recover that value; never substitute replay time.
                    if not item.get("occurred_at"):
                        item["occurred_at"] = item["data"].get("occurred_at") or item["data"].get(
                            "timestamp"
                        )
                    item.setdefault("field_id", item["data"].get("field_id"))
                    # Identity must come from what was persisted with the observation,
                    # never from the current process environment: after a device
                    # replacement or an EDGE_DEVICE_ID change, filling it in at replay
                    # would attribute an old measurement to the wrong device. A legacy
                    # file without a stored device identity is retained, not sent.
                    item.setdefault("device_id", item["data"].get("device_id"))
                    if not all(
                        item.get(key)
                        for key in ("field_id", "device_id", "occurred_at", "idempotency_key")
                    ):
                        raise ValueError("legacy_edge_envelope_incomplete")
                    self._persist(item, path)
                    await self._send(client, item)
                    path.unlink(missing_ok=True)
                    synced += 1
                except Exception as exc:
                    logger.info("Edge queue item retained: %s (%s)", path.name, type(exc).__name__)
                    # Retain a bad item without blocking unrelated observations.
                    continue
        if synced:
            self.last_sync = datetime.now(UTC)
        return synced

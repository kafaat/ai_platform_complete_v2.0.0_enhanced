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

from shared.security.tenant_assertion_headers import tenant_assertion_headers

logger = logging.getLogger(__name__)

# ردودٌ لا تُصلحها إعادةُ المحاولة: الطلب نفسه مرفوض (حقل غير موجود، مخطّط غير صالح،
# تعارض مفتاح). إعادتها كلّ دورة تُنمّي الطابور بلا نهاية وتحجب ما خلفها عن المراقبة،
# فتُنقَل إلى dead-letter للفحص اليدويّ. 5xx/المهلات/أخطاء الشبكة تبقى في الطابور.
PERMANENT_REJECTION_STATUSES = frozenset({400, 404, 409, 422})


def _permanent_rejection_status(exc: BaseException) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in PERMANENT_REJECTION_STATUSES:
            return status
    return None


class CloudSyncService:
    def __init__(
        self,
        cloud_url: str,
        token: str,
        sync_dir: str = "/data/sync_queue",
        dead_letter_dir: str | None = None,
        *,
        agent_token: str = "",
        assertion_key: str = "",
        assertion_key_id: str = "current",
    ):
        self.cloud_url = cloud_url.rstrip("/")
        self.token = token
        self.agent_token = agent_token
        self.assertion_key = assertion_key
        self.assertion_key_id = assertion_key_id or "current"
        self.sync_dir = sync_dir
        # دليلٌ فرعيّ: queue_size/process_queue يقرآن *.json في المستوى الأعلى فقط.
        self.dead_letter_dir = dead_letter_dir or str(Path(sync_dir) / "dead_letter")
        self.last_sync: datetime | None = None
        Path(sync_dir).mkdir(parents=True, exist_ok=True)

    def dead_letter_size(self) -> int:
        path = Path(self.dead_letter_dir)
        return len(list(path.glob("*.json"))) if path.is_dir() else 0

    def _dead_letter(self, path: Path, status: int) -> Path:
        target_dir = Path(self.dead_letter_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name
        os.replace(path, target)
        for directory in (self.sync_dir, str(target_dir)):
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        logger.warning(
            "Edge result rejected permanently (HTTP %s) — moved to dead-letter: %s",
            status,
            target.name,
        )
        return target

    def queue_size(self) -> int:
        return len(list(Path(self.sync_dir).glob("*.json")))

    @staticmethod
    def device_id_for(data: dict) -> str:
        """The device identity an observation would be stored with ('' when there is none)."""
        device_id = data.get("device_id") or os.getenv("EDGE_DEVICE_ID", "")
        return device_id.strip() if isinstance(device_id, str) else ""

    def _envelope(
        self,
        result_type: str,
        data: dict,
        idem_key: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> dict:
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
        if tenant_id is not None and (not isinstance(tenant_id, str) or not tenant_id.strip()):
            raise ValueError("edge_tenant_id_invalid")
        envelope = {
            "type": result_type,
            "data": data,
            "field_id": field_id,
            "device_id": device_id,
            "idempotency_key": idem_key or uuid.uuid4().hex,
            "occurred_at": parsed.isoformat(),
            "queued_at": datetime.now(UTC).isoformat(),
        }
        if tenant_id is not None:
            # W0-07: the tenant the caller signed for travels with the observation, so a replay
            # hours later is still written under that tenant and no other.
            envelope["tenant_id"] = tenant_id
        return envelope

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

    def queue_result(self, result_type: str, data: dict, *, tenant_id: str | None = None):
        return self._persist(self._envelope(result_type, data, tenant_id=tenant_id))

    def _queue_with_key(self, result_type: str, data: dict, idem_key: str):
        return self._persist(self._envelope(result_type, data, idem_key))

    def _headers(self, item: dict) -> dict[str, str]:
        """Service mode for an envelope that carries its tenant; the legacy bearer otherwise.

        Service mode: ``X-Agent-Token`` + a tenant assertion signed with
        ``EDGE_SYNC_TENANT_ASSERTION_KEY`` for this envelope's tenant and this request. A missing key
        raises, so the item stays queued (retried once configured) and is never sent under the
        bearer's tenant instead."""
        tenant_id = item.get("tenant_id")
        if tenant_id:
            if not self.agent_token or len(self.assertion_key) < 32:
                raise ValueError("edge_sync_service_identity_required")
            return {
                "X-Agent-Token": self.agent_token,
                **tenant_assertion_headers(
                    key=self.assertion_key,
                    key_id=self.assertion_key_id,
                    service="edge-inference",
                    tenant_id=str(tenant_id),
                    method="POST",
                    path=self._sync_path(),
                ),
            }
        if not self.token:
            raise ValueError("edge_sync_token_required")
        return {"Authorization": f"Bearer {self.token}"}

    def _sync_path(self) -> str:
        from urllib.parse import urlsplit

        return urlsplit(f"{self.cloud_url}/v1/edge/sync").path

    async def _send(self, client, item: dict) -> None:
        response = await client.post(
            f"{self.cloud_url}/v1/edge/sync",
            json=item,
            headers=self._headers(item),
        )
        response.raise_for_status()
        receipt = response.json()
        if (
            receipt.get("status") not in {"stored", "duplicate_ignored"}
            or receipt.get("idempotency_key") != item["idempotency_key"]
        ):
            raise ValueError("edge_sync_receipt_mismatch")

    async def sync_result(
        self, result_type: str, data: dict, *, tenant_id: str | None = None
    ) -> bool:
        item = self._envelope(result_type, data, tenant_id=tenant_id)
        # Persist BEFORE network I/O. A crash after acceptance still leaves the
        # same key and observation timestamp available for idempotent replay.
        path = self._persist(item)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await self._send(client, item)
            path.unlink(missing_ok=True)
        except Exception as exc:
            status = _permanent_rejection_status(exc)
            if status is not None:
                self._dead_letter(path, status)
                return False
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
                    status = _permanent_rejection_status(exc)
                    if status is not None:
                        self._dead_letter(path, status)
                        continue
                    logger.info("Edge queue item retained: %s (%s)", path.name, type(exc).__name__)
                    # Retain a bad item without blocking unrelated observations.
                    continue
        if synced:
            self.last_sync = datetime.now(UTC)
        return synced

#!/usr/bin/env python3
"""
Cloud Sync Service for Edge Inference
Queues results locally, syncs when connection available
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)


class CloudSyncService:
    """
    Manages offline queue and cloud synchronization for edge devices.
    """

    def __init__(self, cloud_url: str, token: str, sync_dir: str = "/data/sync_queue"):
        self.cloud_url = cloud_url
        self.token = token
        self.sync_dir = sync_dir
        self.last_sync: datetime | None = None

        os.makedirs(sync_dir, exist_ok=True)

    def queue_size(self) -> int:
        """Return number of queued items."""
        try:
            return len([f for f in os.listdir(self.sync_dir) if f.endswith(".json")])
        except OSError:
            return 0

    def queue_result(self, result_type: str, data: dict):
        """Queue a result for later sync.

        Hardening (مراجعة 7): يُولَّد idempotency_key ثابت لكلّ عنصر مرّة
        واحدة عند الحفظ. يُرسَل مع كلّ محاولة → الخادم يكشف التكرار لو نجح
        POST ثمّ انقطعت الشبكة قبل وصول الردّ (إعادة إرسال = نفس المفتاح)."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        # مفتاح ثابت: hash المحتوى + UUID (يميّز عناصر متطابقة المحتوى)
        idem_key = hashlib.sha256(
            f"{result_type}|{json.dumps(data, sort_keys=True, ensure_ascii=False)}|{uuid.uuid4()}".encode()
        ).hexdigest()[:32]
        filename = f"{self.sync_dir}/{result_type}_{timestamp}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "type": result_type,
                    "data": data,
                    "idempotency_key": idem_key,
                    # occurred_at: وقت حدوث القياس على الجهاز (المرجع السببي).
                    # ليس recorded_at — المزامنة قد تتأخّر، لكن السببيّة تعتمد
                    # وقت الحدث لا وقت الوصول (Temporal Authority، مراجعة 9).
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "queued_at": datetime.now(UTC).isoformat(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    async def sync_result(self, result_type: str, data: dict):
        """Sync a single result immediately.

        Hardening (مراجعة 7): يحمل idempotency_key حتّى لو نجح الإرسال ثمّ
        انقطعت الشبكة (الخادم يكشف التكرار). عند الفشل يُحفظ بنفس المفتاح."""
        idem_key = hashlib.sha256(
            f"{result_type}|{json.dumps(data, sort_keys=True, ensure_ascii=False)}|{uuid.uuid4()}".encode()
        ).hexdigest()[:32]
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.cloud_url}/v1/edge/sync",
                    json={
                        "type": result_type,
                        "data": data,
                        "idempotency_key": idem_key,
                        "device_id": os.getenv("EDGE_DEVICE_ID", "unknown"),
                    },
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                resp.raise_for_status()
                self.last_sync = datetime.now(UTC)
                return True
        except Exception as e:
            # Fall back to queue (بنفس المفتاح لتفادي التكرار)
            self._queue_with_key(result_type, data, idem_key)
            logger.info(f"[Sync] Immediate sync failed, queued: {e}")
            return False

    def _queue_with_key(self, result_type: str, data: dict, idem_key: str):
        """يحفظ عنصراً بمفتاح idempotency محدّد مسبقاً (لمسار الفشل)."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{self.sync_dir}/{result_type}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "type": result_type,
                    "data": data,
                    "idempotency_key": idem_key,
                    "queued_at": datetime.now(UTC).isoformat(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    async def process_queue(self) -> int:
        """Process all queued items. Returns count of synced items."""
        synced = 0

        try:
            files = sorted([f for f in os.listdir(self.sync_dir) if f.endswith(".json")])
        except OSError:
            return 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for filename in files:
                filepath = os.path.join(self.sync_dir, filename)

                try:
                    with open(filepath, encoding="utf-8") as f:
                        item = json.load(f)

                    resp = await client.post(
                        f"{self.cloud_url}/v1/edge/sync",
                        json=item,
                        headers={"Authorization": f"Bearer {self.token}"},
                    )

                    if resp.status_code == 200:
                        os.remove(filepath)
                        synced += 1
                    else:
                        logger.info(f"[Sync] Failed to sync {filename}: {resp.status_code}")
                        break  # Stop on first failure

                except Exception as e:
                    logger.info(f"[Sync] Error processing {filename}: {e}")
                    break

        if synced > 0:
            self.last_sync = datetime.now(UTC)

        return synced

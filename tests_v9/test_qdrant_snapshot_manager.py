from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import unquote

import pytest

from scripts.qdrant.snapshot_manager import (
    DRILL_PREFIX,
    QdrantError,
    restore_drill,
    verify,
)

pytestmark = pytest.mark.unit


def test_offline_snapshot_verification_detects_tamper(tmp_path: Path):
    snapshot = tmp_path / "c--s.snapshot"
    snapshot.write_bytes(b"snapshot-bytes")
    manifest = {
        "schema_version": 1,
        "snapshots": [
            {
                "collection": "c",
                "snapshot_file": snapshot.name,
                "size_bytes": snapshot.stat().st_size,
                "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert verify(tmp_path)["snapshots"][0]["collection"] == "c"
    snapshot.write_bytes(b"tampered------")
    with pytest.raises(QdrantError, match="digest mismatch"):
        verify(tmp_path)


def test_manifest_rejects_path_traversal(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "snapshots": [
                    {
                        "collection": "c",
                        "snapshot_file": "../secret",
                        "size_bytes": 1,
                        "sha256": "0" * 64,
                    }
                ]
            }
        )
    )
    with pytest.raises(QdrantError, match="unsafe snapshot filename"):
        verify(tmp_path)


class _RecordingClient:
    """عميل يسجّل النداءات بدل إصدارها — نقيس ما **يُحذَف** فعلاً لا نصّ الشرط."""

    def __init__(self, points_count: int):
        self.calls: list[tuple[str, str]] = []
        self._points = points_count

    def call(self, method, path, body=None, headers=None):
        self.calls.append((method, path))
        return {"result": {"points_count": self._points}}, b""


def _drill_fixture(tmp_path: Path, collection: str = "production_vectors"):
    payload = b"snapshot-bytes"
    snapshot = tmp_path / "prod.snapshot"
    snapshot.write_bytes(payload)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshots": [
                    {
                        "collection": collection,
                        "snapshot_file": snapshot.name,
                        "size_bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "points_count": 7,
                    }
                ],
            }
        )
    )
    return tmp_path


def test_restore_deletion_is_restricted_to_reserved_prefix(tmp_path: Path):
    """كلّ حذف يصدر عن التمرين يقع داخل البادئة المحجوزة — ولا يمسّ مجموعة المصدر.

    الصيغة السابقة كانت تؤكّد سطراً حرفيّاً (`if target.startswith(DRILL_PREFIX)`)؛
    صار في المصدر `if not target.startswith(...)` حارساً fail-closed مع الشرط عند
    الحذف، فسقط التأكيد **بينما الحماية أقوى**. هذه الصيغة تقود الدالّة الحقيقيّة
    وتقيس النداءات: التأكيد على السلوك لا يبيت بإعادة صياغة.
    """
    directory = _drill_fixture(tmp_path)
    client = _RecordingClient(points_count=7)

    restore_drill(client, directory, tmp_path / "evidence.json")

    deletes = [path for method, path in client.calls if method == "DELETE"]
    assert deletes, "لم يُحذف شيء — التمرين يجب أن ينظّف مجموعته المؤقّتة"
    for path in deletes:
        target = unquote(path.removeprefix("/collections/"))
        assert target.startswith(DRILL_PREFIX), f"حذف خارج البادئة المحجوزة: {target}"
        assert "production_vectors" != target, "حُذفت مجموعة المصدر"

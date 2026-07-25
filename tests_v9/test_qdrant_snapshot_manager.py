from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.qdrant.snapshot_manager import QdrantError, verify


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


def test_restore_deletion_is_restricted_to_reserved_prefix():
    src = (Path(__file__).parents[1] / "scripts/qdrant/snapshot_manager.py").read_text()
    assert 'DRILL_PREFIX = "sahool_restore_drill_"' in src
    assert "if target.startswith(DRILL_PREFIX)" in src

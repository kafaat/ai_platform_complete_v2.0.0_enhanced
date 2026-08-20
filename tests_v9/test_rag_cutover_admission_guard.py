from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/architecture/rag_cutover_admission_guard.py"


def _run(*args: str):
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=60,
    )
    return p.returncode, json.loads(p.stdout)


def _receipt(tmp_path: Path, subject: str) -> Path:
    data = {
        "schema": "sahool.rag-live-parity-receipt/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "subject_sha": subject,
        "embedding_contract_sha256": hashlib.sha256(
            (ROOT / "docs/architecture/rag_embedding_contract.json").read_bytes()
        ).hexdigest(),
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
        "collection": "sahool_agri_kb",
        "vector_size": 768,
        "query_count": 5,
        "comparable_query_count": 5,
        "min_jaccard": 0.8,
        "mean_jaccard": 0.9,
        "read_only": True,
        "authority_promotion": False,
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_admission_requires_live_receipt():
    rc, out = _run()
    assert rc == 2
    assert out["status"] == "EVIDENCE_REQUIRED"
    assert out["authority_changed"] is False


def test_valid_live_parity_is_still_blocked_by_revocation_readiness(tmp_path):
    subject = "b" * 40
    receipt = _receipt(tmp_path, subject)
    rc, out = _run("--receipt", str(receipt), "--subject-sha", subject)
    assert rc == 1
    assert out["status"] == "BLOCKED"
    assert out["cutover_capable"] is False
    assert "direct_qdrant_revocation_ready" in out["blocking_requirements"]
    assert "direct_response_path_exception_present:local-ai-rag" in out["blocking_requirements"]
    assert out["authority_changed"] is False


def test_receipt_subject_mismatch_fails(tmp_path):
    receipt = _receipt(tmp_path, "c" * 40)
    rc, out = _run("--receipt", str(receipt), "--subject-sha", "d" * 40)
    assert rc == 1
    assert out["status"] == "FAILED"
    assert "live_parity_receipt_invalid" in out["findings"]

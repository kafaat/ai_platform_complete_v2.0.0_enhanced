"""نسبُ الكشف — منطقٌ صرف وعقدُ الهجرة بلا قاعدة (v239 ``detection_provenance``).

* الحافّة: بصمةُ المصنوعة تُؤخَذ من **حكم البوّابة** (``actual_sha256`` المُتحقَّق) وبصمةُ
  المدخل من بايتات الصورة؛ حكمٌ غيرُ مُتحقَّق لا يُنتِج نسباً.
* المنصّة: صفٌّ لكلّ كشف، ``calibrated`` لا يُدّعى من الجهاز، والنتيجةُ بلا كتلة نسب تُسجَّل
  ``unattested_legacy`` لا تُسقَط، وكتلةٌ مشوَّهة تُرفَض.
* الهجرة: ذرّيّة، RLS+FORCE، مُسجَّلة قبل v206 في المُشغّلَين.

الشاهدُ الحيّ (دورٌ مقيَّد، عزلُ المستأجرين): ``test_v239_detection_provenance_live_pg.py``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_MIG = _ROOT / "migrations" / "v239_detection_provenance.sql"
_SHA = hashlib.sha256(b"pest-bytes").hexdigest()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_GATE = _load(
    "edge_gate_provenance_contract", _ROOT / "services/edge-inference/model_artifact_gate.py"
)
_PLATFORM = _load(
    "platform_detection_provenance_contract",
    _ROOT / "services/sahool-platform/api/edge_models.py",
)


def _capability(**over):
    return {"active": True, "sha256_verified": True, "actual_sha256": _SHA, **over}


# ── الحافّة ─────────────────────────────────────────────────────────────
def test_edge_provenance_takes_the_artifact_sha_from_the_gate_verdict():
    block = _GATE.detection_provenance(
        model_id="pest_detector_int8.onnx",
        model_version="2026.1-edge",
        capability=_capability(),
        image_bytes=b"leaf",
        threshold=0.6,
    )
    assert block["artifact_sha256"] == _SHA
    assert block["input_sha256"] == hashlib.sha256(b"leaf").hexdigest()
    assert block["threshold"] == 0.6
    assert block["calibrated"] is False
    assert block["schema"] == _PLATFORM.PROVENANCE_SCHEMA


@pytest.mark.parametrize(
    "over",
    [
        {"active": False},
        {"sha256_verified": False},
        {"actual_sha256": None},
        {"actual_sha256": "not-a-digest"},
    ],
)
def test_edge_refuses_provenance_for_an_unverified_artifact(over):
    with pytest.raises(ValueError, match="model_artifact_not_verified"):
        _GATE.detection_provenance(
            model_id="m",
            model_version="v",
            capability=_capability(**over),
            image_bytes=b"leaf",
            threshold=0.6,
        )


def test_edge_and_platform_agree_on_the_block_schema():
    """ما تُنتِجه الحافّة تقبله المنصّة حرفيّاً — لا مخطّطان ينجرفان."""
    block = _GATE.detection_provenance(
        model_id="pest_detector_int8.onnx",
        model_version="2026.1-edge",
        capability=_capability(),
        image_bytes=b"leaf",
        threshold=0.6,
    )
    rows = _PLATFORM.provenance_rows(
        "pest_detection",
        {"detections": [{"class_name": "aphid", "confidence": 0.9}], "provenance": block},
    )
    assert rows[0]["artifact_sha256"] == _SHA and rows[0]["attestation"] == "attested"


# ── المنصّة ─────────────────────────────────────────────────────────────
def _block(**over):
    return {
        "schema": "sahool.detection-provenance/v1",
        "model_id": "pest_detector_int8.onnx",
        "model_version": "2026.1-edge",
        "artifact_sha256": _SHA,
        "input_sha256": hashlib.sha256(b"leaf").hexdigest(),
        "threshold": 0.6,
        "calibrated": True,
        **over,
    }


def test_platform_writes_one_attested_row_per_detection_and_never_trusts_calibration():
    rows = _PLATFORM.provenance_rows(
        "pest_detection",
        {
            "detections": [
                {"class_name": "aphid", "confidence": 0.93},
                {"class_name": "rust", "confidence": 0.71},
            ],
            "provenance": _block(),
        },
    )
    assert [r["detection_index"] for r in rows] == [0, 1]
    assert [r["score"] for r in rows] == [0.93, 0.71]
    assert all(r["artifact_sha256"] == _SHA for r in rows)
    assert all(r["calibrated"] is False and r["calibration_ref"] is None for r in rows)


def test_a_result_without_a_provenance_block_is_recorded_as_unattested_not_dropped():
    rows = _PLATFORM.provenance_rows(
        "pest_detection",
        {"detections": [{"class_name": "aphid", "confidence": 0.9}], "model_version": "old"},
    )
    assert len(rows) == 1
    assert rows[0]["attestation"] == "unattested_legacy"
    assert rows[0]["artifact_sha256"] is None and rows[0]["input_sha256"] is None
    assert rows[0]["model_version"] == "old"


@pytest.mark.parametrize(
    ("block", "reason"),
    [
        (_block(schema="other/v9"), "provenance_schema_unknown"),
        (_block(artifact_sha256="abc"), "artifact_sha256_invalid"),
        (_block(input_sha256=None), "input_sha256_invalid"),
        (_block(threshold=1.5), "threshold_out_of_range"),
        (_block(threshold=True), "threshold_not_a_number"),
        (_block(model_id=""), "model_id_invalid"),
        ("not-a-dict", "provenance_not_an_object"),
    ],
)
def test_a_malformed_provenance_claim_is_rejected(block, reason):
    with pytest.raises(ValueError, match=reason):
        _PLATFORM.provenance_rows(
            "pest_detection",
            {"detections": [{"class_name": "aphid", "confidence": 0.9}], "provenance": block},
        )


@pytest.mark.parametrize("score", [1.2, -0.1, float("nan"), "0.9", None])
def test_a_detection_without_a_unit_interval_score_is_rejected(score):
    with pytest.raises(ValueError, match="score_"):
        _PLATFORM.provenance_rows(
            "pest_detection", {"detections": [{"confidence": score}], "provenance": _block()}
        )


def test_result_types_without_detections_carry_no_provenance():
    assert _PLATFORM.provenance_rows("yield_estimate", {"detections": [{"x": 1}]}) == []


# ── الهجرة ─────────────────────────────────────────────────────────────
def _entries() -> list[str]:
    text = (_ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip().endswith(".sql") and not ln.lstrip().startswith("#")
    ]


def test_v239_is_registered_before_v206_in_both_runners():
    entries = _entries()
    assert entries[-1] == "v206_rls_final_hardening.sql"
    assert entries.index(_MIG.name) < entries.index("v206_rls_final_hardening.sql")
    runner = (_ROOT / "scripts_v9/run_migrations.sql").read_text(encoding="utf-8")
    assert runner.index(f"migrations/{_MIG.name}") < runner.index(
        "migrations/v206_rls_final_hardening.sql"
    )


def test_v239_is_atomic_rls_forced_and_tenant_bound():
    code = "\n".join(ln.split("--", 1)[0] for ln in _MIG.read_text(encoding="utf-8").splitlines())
    assert code.lstrip().startswith("BEGIN;") and code.rstrip().endswith("COMMIT;")
    assert "ENABLE ROW LEVEL SECURITY" in code and "FORCE ROW LEVEL SECURITY" in code
    assert "NULLIF(current_setting('app.current_tenant', true), '')" in code
    assert "REFERENCES edge_results (id, tenant_id)" in code
    assert "calibrated = (calibration_ref IS NOT NULL)" in code
    assert "IS NULL OR" not in code.split("CREATE POLICY", 1)[1].split(";", 1)[0]

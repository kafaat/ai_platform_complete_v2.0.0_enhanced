from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/s5_exec_01_writer_cutover_guard.py"
spec = importlib.util.spec_from_file_location("s5_exec_01_writer_cutover_guard", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _sandbox(tmp_path: Path, monkeypatch):
    freeze = json.loads(
        (ROOT / "docs/architecture/s5_exec_01_edge_freeze.json").read_text(encoding="utf-8")
    )
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/s5_exec_01_edge_freeze.json").write_text(
        json.dumps(freeze), encoding="utf-8"
    )
    for item in freeze["writer_cutover_set_runtime_only"]:
        for rel in item["writers"]:
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
    # مُدخَلا GATE-01 يُنسَخان أيضاً: قرار التأجيل يُقاس منهما، فتركُهما مُشيرَين إلى
    # الشجرة الحقيقيّة كان سيجعل حالات التأجيل تقيس شيئاً لا تتحكّم فيه.
    policy_dst = tmp_path / "docs/architecture/gate01_policy.json"
    policy_dst.write_text(
        (ROOT / "docs/architecture/gate01_policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    adj_dst = tmp_path / "docs/architecture/gates/adjudications"
    adj_dst.mkdir(parents=True, exist_ok=True)
    for adjudication in sorted((ROOT / "docs/architecture/gates/adjudications").glob("*.json")):
        (adj_dst / adjudication.name).write_text(
            adjudication.read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "FREEZE", tmp_path / "docs/architecture/s5_exec_01_edge_freeze.json")
    monkeypatch.setattr(mod, "GATE01_POLICY", policy_dst)
    monkeypatch.setattr(mod, "GATE01_ADJUDICATIONS", adj_dst)
    return freeze


def _open_the_gate(tmp_path: Path):
    p = tmp_path / "docs/architecture/gate01_policy.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["gate"]["state"] = "OPEN"
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _stamp_adjudication(tmp_path: Path, status: str):
    adjudication = next((tmp_path / "docs/architecture/gates/adjudications").glob("*.json"))
    doc = json.loads(adjudication.read_text(encoding="utf-8"))
    doc["status"] = status
    doc.setdefault("allowed_paths", []).append(
        "services/sahool-platform/api/phase_runtime_store.py"
    )
    adjudication.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_current_frozen_writer_set_has_cutover_contracts():
    assert mod.findings() == []


def test_new_frozen_writer_without_contract_fails_closed(tmp_path, monkeypatch):
    freeze = _sandbox(tmp_path, monkeypatch)
    freeze["writer_cutover_set_runtime_only"][0]["writers"].append(
        "services/sahool-platform/api/new_writer.py"
    )
    (tmp_path / "docs/architecture/s5_exec_01_edge_freeze.json").write_text(
        json.dumps(freeze), encoding="utf-8"
    )
    assert any("FROZEN_WRITER_WITHOUT_CUTOVER_CONTRACT" in x for x in mod.findings())


def test_removing_strict_mode_marker_is_blocked(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    rel = "services/sahool-platform/api/routers/recommendations.py"
    p = tmp_path / rel
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "if mode.strict_decision_service_required:", "if False:", 1
        ),
        encoding="utf-8",
    )
    assert any("CUTOVER_MARKER_MISSING recommendation_outcomes" in x for x in mod.findings())


def test_dispatch_writer_must_be_retired_in_strict_mode(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    rel = "services/sahool-platform/api/routers/decision_dispatch.py"
    p = tmp_path / rel
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "legacy_dispatch_writer_retired_after_decision_sor_cutover",
            "legacy_dispatch_still_live",
            1,
        ),
        encoding="utf-8",
    )
    assert any("CUTOVER_MARKER_MISSING dispatch_decisions" in x for x in mod.findings())


# ── التأجيل ببوّابة: مقبولٌ ما دامت تمنع، وينقضي بنفسه لحظةَ توقّفها ──────────────
# العطل الذي تمنعه هذه الحالات: أن يصير «مؤجَّل ببوّابة» عذراً دائماً يبقى بعد زوال
# سببه، فيُقرأ الأخضر «قُطِع كلّ الكتّاب» وقد بقي أحدهم غير مقطوع بلا مانع.

_DEFERRED_PAIR = (
    "services/sahool-platform/api/phase_runtime_store.py",
    "online_learning_updates",
)


def test_gate01_deferred_writer_is_accepted_only_while_the_gate_actually_blocks():
    """على الشجرة الحقيقيّة: المسار مجمَّد · البوّابة CLOSED · لا تفويض ISSUED يغطّيه."""
    assert _DEFERRED_PAIR in mod.GATE01_DEFERRED
    assert mod._gate01_blocks(_DEFERRED_PAIR[0]) is True
    assert mod.findings() == []
    assert _DEFERRED_PAIR in mod.deferred_pairs()  # مُعلَنٌ لا صامت


def test_gate01_deferral_expires_when_the_gate_opens(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    _open_the_gate(tmp_path)
    found = mod.findings()
    assert any("GATE01_DEFERRAL_NO_LONGER_JUSTIFIED online_learning_updates" in x for x in found)
    # ويُفرَض العقد فعلاً بعد سقوط العذر — لا يُكتفى بتسميته.
    assert any("CUTOVER_MARKER_MISSING online_learning_updates" in x for x in found)
    assert mod.deferred_pairs() == []


def test_gate01_deferral_expires_when_an_issued_adjudication_covers_the_path(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    _stamp_adjudication(tmp_path, "ISSUED")
    assert any(
        "GATE01_DEFERRAL_NO_LONGER_JUSTIFIED online_learning_updates" in x for x in mod.findings()
    )


def test_a_consumed_adjudication_does_not_lift_the_deferral(tmp_path, monkeypatch):
    """المُستهلَك ليس إذناً — وإلّا صار كلّ تفويضٍ قديم مفتاحاً دائماً."""
    _sandbox(tmp_path, monkeypatch)
    _stamp_adjudication(tmp_path, "CONSUMED")
    assert mod.findings() == []

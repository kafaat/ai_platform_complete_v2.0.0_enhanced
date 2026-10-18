from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import date
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
    # This sandbox exercises the historical ISSUED U07 patch, not today's live
    # tree. Later independent migrations legitimately change MANIFEST, while the
    # consumed U07 grant must retain its original byte pins. Read those exact
    # immutable Git objects; never rebind the grant or patch the validator.
    # The unit CI checkout fetches full history, as the repository gates require.
    for rel, blob in mod._U07_BLOBS.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT))
        assert mod.GATE01.blob_sha(rel, root=tmp_path) == blob
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
    # Exercise the issued case independently of the live record's later consumption
    # and the wall clock. Only this sandbox copy changes; live-tree checks remain live.
    u07_path = adj_dst / f"{mod._U07_ID}.json"
    u07 = json.loads(u07_path.read_text(encoding="utf-8"))
    u07["status"] = "ISSUED"
    u07.pop("consumption", None)
    u07_path.write_text(json.dumps(u07), encoding="utf-8")

    class IssuedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 16)

    monkeypatch.setattr(mod.GATE01, "date", IssuedDate)
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
    adjudication = tmp_path / "docs/architecture/gates/adjudications" / f"{mod._U07_ID}.json"
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
    """على الشجرة الحقيقيّة: المسار مجمَّد · البوّابة CLOSED · رقعة U07 وحدها لا تأذن بقطع SoR."""
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


def _u07_document(tmp_path: Path):
    path = tmp_path / "docs/architecture/gates/adjudications" / f"{mod._U07_ID}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_exact_u07_bytes_preserve_cutover_deferral_without_opening_gate(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    assert mod._gate01_blocks(_DEFERRED_PAIR[0])
    assert mod.findings() == []
    assert mod.deferred_pairs() == [_DEFERRED_PAIR]
    policy = json.loads(mod.GATE01_POLICY.read_text(encoding="utf-8"))
    _, doc = _u07_document(tmp_path)
    errors, used = mod.GATE01.evaluate(
        list(mod._U07_BLOBS),
        policy,
        [doc],
        {p: mod.GATE01.blob_sha(p, root=tmp_path) for p in mod._U07_BLOBS},
    )
    assert errors == [] and used == mod._U07_ID
    assert policy["gate"]["state"] == "CLOSED"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("adjudication_id", "GATE01-ADJ-OTHER"),
        ("schema", "unknown"),
        ("gate_id", "GATE-OTHER"),
        ("allowed_paths", ["services/sahool-platform/api/phase_runtime_store.py"]),
        ("allowed_paths", list(mod._U07_BLOBS) + ["services/sahool-platform/api/event_bus.py"]),
        ("allowed_gap_closures", ["REPORT3-U07-REVIEW-DECISION-NOT-PERSISTED-01", "SoR"]),
        ("allowed_gap_closures", []),
        ("one_time", False),
        ("one_time", 1),
        ("adjudicated_on", "2026-10-15"),
        ("expires_on", "2099-01-01"),
        ("expires_on", "2026-10-15"),
        ("phase0_baseline_ref", {"commit_sha": mod._U07_BASELINE, "must_match_policy": False}),
        ("bindings", {"require_patch_digest": False}),
        ("authorized_patch_sha256", "0" * 64),
        ("authorized_blobs", {}),
    ],
)
def test_u07_label_cannot_authorize_other_scope_or_relaxed_bindings(
    tmp_path, monkeypatch, key, value
):
    _sandbox(tmp_path, monkeypatch)
    path, doc = _u07_document(tmp_path)
    doc[key] = value
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])
    assert any("GATE01_DEFERRAL_NO_LONGER_JUSTIFIED" in item for item in mod.findings())


@pytest.mark.parametrize("path", list(mod._U07_BLOBS))
def test_actual_changed_bytes_cannot_borrow_the_u07_scope(tmp_path, monkeypatch, path):
    _sandbox(tmp_path, monkeypatch)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n# changed bytes\n")
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])


def test_rebinding_new_bytes_under_the_same_u07_id_is_not_reviewed(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    target = tmp_path / "migrations/MANIFEST.txt"
    target.write_bytes(target.read_bytes() + b"\n# different scope\n")
    path, doc = _u07_document(tmp_path)
    doc["authorized_blobs"]["migrations/MANIFEST.txt"] = mod.GATE01.blob_sha(
        "migrations/MANIFEST.txt", root=tmp_path
    )
    doc["authorized_patch_sha256"] = mod.GATE01.canonical_patch_digest(doc["authorized_blobs"])
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])


def test_u07_expiry_is_evaluated_by_the_unchanged_gate_validator(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)

    class ExpiredDate:
        @staticmethod
        def today():
            return date(2026, 10, 24)

        fromisoformat = date.fromisoformat

    monkeypatch.setattr(mod.GATE01, "date", ExpiredDate)
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])


def test_consumed_u07_is_not_reused_as_an_authorization(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    path, doc = _u07_document(tmp_path)
    doc["status"] = "CONSUMED"
    path.write_text(json.dumps(doc), encoding="utf-8")
    # The prior semantics remain: no live grant means GATE-01 blocks cutover.
    assert mod._gate01_blocks(_DEFERRED_PAIR[0])
    policy = json.loads(mod.GATE01_POLICY.read_text(encoding="utf-8"))
    assert not mod._review_only_u07_authorization(doc, policy)


def test_correlation_grant_cannot_authorize_u07_writer_or_cutover(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    path, u07 = _u07_document(tmp_path)
    u07["status"] = "CONSUMED"
    path.write_text(json.dumps(u07), encoding="utf-8")
    # Put today's real MANIFEST back: no historical U07 authorization is being
    # replayed. The separate correlation grant cannot authorize this writer.
    (tmp_path / "migrations/MANIFEST.txt").write_bytes(
        (ROOT / "migrations/MANIFEST.txt").read_bytes()
    )
    correlation_path = mod.GATE01_ADJUDICATIONS / "GATE01-ADJ-2026-10-16-002.json"
    correlation = json.loads(correlation_path.read_text(encoding="utf-8"))
    assert set(correlation["allowed_paths"]) == {
        "migrations/MANIFEST.txt",
        "docs/architecture/db_ownership.yml",
    }
    assert _DEFERRED_PAIR[0] not in correlation["allowed_paths"]
    policy = json.loads(mod.GATE01_POLICY.read_text(encoding="utf-8"))
    errors, used = mod.GATE01.evaluate(
        [_DEFERRED_PAIR[0]],
        policy,
        [correlation],
        {_DEFERRED_PAIR[0]: mod.GATE01.blob_sha(_DEFERRED_PAIR[0], root=tmp_path)},
    )
    assert errors and used is None
    assert policy["gate"]["state"] == "CLOSED"
    assert mod._gate01_blocks(_DEFERRED_PAIR[0])
    assert mod.deferred_pairs() == [_DEFERRED_PAIR]
    assert mod.findings() == []


def test_another_issued_grant_still_revokes_deferral_alongside_valid_u07(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    _, doc = _u07_document(tmp_path)
    doc["adjudication_id"] = "GATE01-ADJ-ANOTHER-ISSUED"
    (mod.GATE01_ADJUDICATIONS / "other.json").write_text(json.dumps(doc), encoding="utf-8")
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])


def test_gate_validator_failure_cannot_be_replaced_by_local_scope_match(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.setattr(mod.GATE01, "evaluate", lambda *_: (["rejected"], None))
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])


@pytest.mark.parametrize(
    "key",
    [
        "require_patch_digest",
        "require_paths_subset",
        "require_baseline_match",
        "require_exact_head_sha",
    ],
)
def test_u07_binding_booleans_are_not_integer_aliases(tmp_path, monkeypatch, key):
    _sandbox(tmp_path, monkeypatch)
    path, doc = _u07_document(tmp_path)
    doc["bindings"][key] = int(doc["bindings"][key])
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])


def test_missing_pinned_manifest_does_not_qualify(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    (tmp_path / "migrations/MANIFEST.txt").unlink()
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])


@pytest.mark.parametrize("change", ["baseline", "manifest_not_frozen"])
def test_u07_scope_requires_the_reviewed_policy_binding(tmp_path, monkeypatch, change):
    _sandbox(tmp_path, monkeypatch)
    policy = json.loads(mod.GATE01_POLICY.read_text(encoding="utf-8"))
    if change == "baseline":
        policy["phase0_baseline"]["commit_sha"] = "0" * 40
    else:
        policy["frozen_paths"].remove("migrations/MANIFEST.txt")
    mod.GATE01_POLICY.write_text(json.dumps(policy), encoding="utf-8")
    assert not mod._gate01_blocks(_DEFERRED_PAIR[0])

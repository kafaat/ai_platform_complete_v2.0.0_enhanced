"""تكذيب حارس GATE-01 — بوّابةُ تفويضٍ مقيَّد، لا مفتاحٌ ثنائيّ.

الخصائص المقيسة، وكلٌّ منها فرعٌ حاجب:

- مسارٌ غير مجمَّد ⇒ يمرّ · مجمَّدٌ بلا تفويض ⇒ يُحجَب.
- بوّابةٌ ``OPEN`` ⇒ الدلالة القديمة تبقى · وأيّ حالةٍ أخرى تفشل **مغلقة**.
- تفويضٌ مطابق تماماً ⇒ يمرّ · وأيّ انحرافٍ عنه ⇒ يُحجَب: بوّابةٌ أخرى · أساسٌ مخالف
  · مسارٌ مجمَّد زائد · بايتاتٌ تغيّرت · بصمةٌ تناقض بصماتها · مُستهلَك أو ملغى ·
  مخطَّطٌ مجهول · بلا مسارات.
- والسياسة نفسها تُتحقَّق: مخطَّطٌ غريب أو قائمةٌ فارغة ⇒ فشلٌ مغلق (موروثةٌ من #836).

**والفرق بين هذه وسابقتها ليس عدد الحالات:** الصيغة الأولى كانت تسأل «أمفتوحةٌ أم
مغلقة؟» فلا تُمثِّل إذناً مقيَّداً أصلاً. وهذه تسأل «أهذا المسّ بعينه مأذونٌ بهذه
البايتات بعينها؟».
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "gate01_frozen_path_guard.py"
_POLICY = _ROOT / "docs" / "architecture" / "gate01_policy.json"
_ADJ_DIR = _ROOT / "docs" / "architecture" / "gates" / "adjudications"

_spec = importlib.util.spec_from_file_location("g01", _GUARD)
guard = importlib.util.module_from_spec(_spec)
sys.modules["g01"] = guard
_spec.loader.exec_module(guard)

_FROZEN_A = "services/actuator-service/actuator_runtime.py"
_FROZEN_B = "services/actuator-service/routers/commands.py"
_FROZEN_C = "services/sahool-platform/api/event_bus.py"


def _policy(state="CLOSED"):
    return {
        "schema": "sahool.gate01_policy/v2",
        "gate": {"id": "GATE-01", "gap_id": "GAP-X", "state": state},
        "phase0_baseline": {"commit_sha": "b" * 40},
        "frozen_paths": [_FROZEN_A, _FROZEN_B, _FROZEN_C],
    }


_BLOBS = {_FROZEN_A: "a" * 40, _FROZEN_B: "c" * 40, _FROZEN_C: "e" * 40}


def _adj(**over):
    blobs = over.pop("authorized_blobs", {_FROZEN_A: "a" * 40, _FROZEN_B: "c" * 40})
    d = {
        "schema": "sahool.gate01_adjudication/v1",
        "adjudication_id": "ADJ-TEST-001",
        "gate_id": "GATE-01",
        "status": "ISSUED",
        "phase0_baseline_ref": {"commit_sha": "b" * 40},
        "allowed_paths": sorted(blobs),
        "authorized_blobs": blobs,
        "authorized_patch_sha256": guard.canonical_patch_digest(blobs),
        "bindings": {"require_patch_digest": True},
    }
    d.update(over)
    return d


def _run(changed, policy=None, adjs=None, blobs=None):
    return guard.evaluate(changed, policy or _policy(), adjs or [], blobs or _BLOBS)


# ── ١) لا مسارَ مجمَّداً ⇒ يمرّ ────────────────────────────────────────────────
def test_an_untouched_frozen_path_passes():
    errors, used = _run(["README.md", "scripts/ci/whatever.py"])
    assert errors == []
    assert used is None


# ── ٢) مجمَّدٌ بلا تفويض ⇒ يُحجَب ──────────────────────────────────────────────
def test_touching_a_frozen_path_is_blocked():
    errors, used = _run([_FROZEN_A])
    assert errors and used is None


def test_the_message_names_the_gap_and_the_way_out():
    errors, _ = _run([_FROZEN_A])
    joined = "\n".join(errors)
    assert "GAP-X" in joined
    assert "أرجِع الملفّ" in joined or "تفويضاً" in joined


# ── ٣) الدلالة القديمة تبقى: OPEN يمرّ، وغيرها يفشل مغلقاً ────────────────────
def test_an_open_gate_lets_the_same_change_through():
    errors, _ = _run([_FROZEN_A], policy=_policy(state="OPEN"))
    assert errors == []


@pytest.mark.parametrize("state", ["CLOSED", "closed", "", "PENDING", None, "OPENISH"])
def test_any_state_that_is_not_open_fails_closed(state):
    errors, _ = _run([_FROZEN_A], policy=_policy(state=state))
    assert errors, f"حالة {state!r} مرّت وهي ليست OPEN"


# ── ٤) التفويض المطابق تماماً ⇒ يمرّ ──────────────────────────────────────────
def test_an_exactly_matching_authorization_permits_only_its_own_paths():
    errors, used = _run([_FROZEN_A, _FROZEN_B], adjs=[_adj()])
    assert errors == []
    assert used == "ADJ-TEST-001"


# ── ٥) مسارٌ مجمَّد زائد على المأذون ⇒ يُحجَب ────────────────────────────────
def test_an_extra_frozen_path_beyond_the_authorization_is_blocked():
    errors, used = _run([_FROZEN_A, _FROZEN_B, _FROZEN_C], adjs=[_adj()])
    assert used is None
    assert any("خارج المأذون" in e for e in errors)


# ── ٦) بايتاتٌ تغيّرت بعد الإذن ⇒ يُحجَب ─────────────────────────────────────
def test_a_single_changed_byte_invalidates_the_authorization():
    drifted = dict(_BLOBS, **{_FROZEN_A: "f" * 40})
    errors, used = _run([_FROZEN_A, _FROZEN_B], adjs=[_adj()], blobs=drifted)
    assert used is None
    assert any("بايتاتُ الشجرة تخالف المأذون" in e for e in errors)


# ── ٧) تفويضٌ يناقض نفسه (بصمةٌ لا تُشتقّ من بصماته) ⇒ يُحجَب ────────────────
def test_a_forged_patch_digest_is_rejected():
    errors, used = _run([_FROZEN_A, _FROZEN_B], adjs=[_adj(authorized_patch_sha256="0" * 64)])
    assert used is None
    assert any("يناقض نفسه" in e for e in errors)


# ── ٨) أساسٌ مخالف للمُجمَّد ⇒ يُحجَب ────────────────────────────────────────
def test_an_authorization_against_a_different_baseline_is_rejected():
    errors, used = _run(
        [_FROZEN_A, _FROZEN_B], adjs=[_adj(phase0_baseline_ref={"commit_sha": "9" * 40})]
    )
    assert used is None
    assert any("الأساس" in e for e in errors)


# ── ٩) مُستهلَكٌ أو ملغى ⇒ يُحجَب (لا يُعاد استعماله) ────────────────────────
@pytest.mark.parametrize("status", ["CONSUMED", "REVOKED", "", None])
def test_a_consumed_or_revoked_authorization_cannot_be_reused(status):
    errors, used = _run([_FROZEN_A, _FROZEN_B], adjs=[_adj(status=status)])
    assert used is None
    assert any("ISSUED" in e for e in errors)


# ── ١٠) تفويضٌ مشوَّه ⇒ فشلٌ مغلق ────────────────────────────────────────────
@pytest.mark.parametrize(
    "over, ident",
    [
        ({"schema": "something/else"}, "unknown-schema"),
        ({"gate_id": "GATE-99"}, "other-gate"),
        ({"allowed_paths": [], "authorized_blobs": {}}, "no-paths"),
    ],
    ids=["unknown-schema", "other-gate", "no-paths"],
)
def test_a_malformed_authorization_fails_closed(over, ident):
    errors, used = _run([_FROZEN_A], adjs=[_adj(**over)])
    assert used is None and errors


def test_an_authorization_for_another_gate_does_not_authorise_this_one():
    errors, used = _run([_FROZEN_A, _FROZEN_B], adjs=[_adj(gate_id="GATE-99")])
    assert used is None
    assert any("بوّابةٍ أخرى" in e for e in errors)


# ── السياسة نفسها تُتحقَّق (موروثة من #836) ──────────────────────────────────
def test_a_missing_policy_file_fails_closed(tmp_path):
    with pytest.raises(OSError):
        guard.load_policy(tmp_path / "absent.json")


def test_a_wrong_schema_fails_closed(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"schema": "other/v1", "frozen_paths": ["x"]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
        guard.load_policy(p)


def test_an_empty_frozen_list_fails_closed(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(
        json.dumps({"schema": "sahool.gate01_policy/v2", "frozen_paths": []}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="EMPTY_FROZEN_LIST"):
        guard.load_policy(p)


# ── الشجرة الحيّة ────────────────────────────────────────────────────────────
def test_the_live_policy_is_readable_and_globally_closed():
    """البوّابة تبقى مغلقة عالميّاً — التفويض المقيَّد لا يفتحها."""
    policy = guard.load_policy(_POLICY)
    assert policy["gate"]["state"] == "CLOSED"
    assert policy["phase0_baseline"]["commit_sha"]


def test_every_live_adjudication_is_self_consistent():
    """تفويضٌ منشورٌ لا تُشتقّ بصمتُه من بصماته تناقضٌ يُقرأ إذناً — فيُفحَص هنا."""
    for adj in guard.load_adjudications(_ADJ_DIR):
        blobs = adj["authorized_blobs"]
        assert sorted(blobs) == sorted(adj["allowed_paths"])
        assert guard.canonical_patch_digest(blobs) == adj["authorized_patch_sha256"], (
            f"{adj['adjudication_id']}: بصمةٌ لا تُشتقّ من بصماتها"
        )
        assert set(adj["allowed_paths"]) <= set(guard.load_policy(_POLICY)["frozen_paths"])


def test_the_live_authorization_matches_the_tree_it_authorises():
    """البايتات المأذونة هي بايتات الشجرة — وإلّا فالتفويض بائتٌ ويجب تجديده."""
    for adj in guard.load_adjudications(_ADJ_DIR):
        if adj.get("status") != "ISSUED":
            continue
        for path, declared in adj["authorized_blobs"].items():
            assert guard.blob_sha(path) == declared, f"{path}: بايتاتٌ تخالف التفويض"


def test_a_frozen_path_absent_from_the_tree_is_declared_absent():
    policy = guard.load_policy(_POLICY)
    declared_absent = set(policy.get("not_yet_in_tree") or [])
    for path in policy["frozen_paths"]:
        assert (_ROOT / path).exists() or path in declared_absent, path


def test_the_real_reverted_patch_would_still_be_caught_without_its_authorization():
    """بلا تفويضٍ مطابق، المسّ نفسه يُحجَب — فالإذن هو الفارق لا تليينُ الحارس."""
    policy = guard.load_policy(_POLICY)
    errors, used = guard.evaluate([_FROZEN_A, _FROZEN_B], policy, [], _BLOBS)
    assert used is None and errors


def test_the_live_tree_is_permitted_only_by_an_exact_authorization():
    """والشجرة الحاليّة تمرّ **بتفويضها** لا بغيابه — الفرق يُقاس لا يُفترَض."""
    policy = guard.load_policy(_POLICY)
    blobs = {p: guard.blob_sha(p) for p in policy["frozen_paths"]}
    adjs = guard.load_adjudications(_ADJ_DIR)
    errors, used = guard.evaluate([_FROZEN_A, _FROZEN_B], policy, adjs, blobs)
    assert errors == [], errors
    assert used == "GATE01-ADJ-2026-08-13-001"

    stripped = [copy.deepcopy(a) for a in adjs]
    for a in stripped:
        a["status"] = "CONSUMED"
    errors2, used2 = guard.evaluate([_FROZEN_A, _FROZEN_B], policy, stripped, blobs)
    assert used2 is None and errors2, "تفويضٌ مُستهلَك مرّ — الاستعمال مرّةً واحدة غير مفروض"

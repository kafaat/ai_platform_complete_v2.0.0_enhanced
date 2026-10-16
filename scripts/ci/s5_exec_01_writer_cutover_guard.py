#!/usr/bin/env python3
"""Fail closed unless every frozen S5-EXEC-01 platform writer has a single-authority end state.

The writer inventory comes exclusively from the generated edge-freeze artifact.  This guard
never re-derives edge_class or writer identity lexically.  It verifies the code-side cutover
contract for each frozen writer while the pre-cutover bridge remains physically present.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: سطرُ التأجيل الذي أضفتُه
# عربيّ، و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان الحارس يحسب **صحيحاً** ثمّ
# يموت وهو يطبع نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وقد مرّ.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/architecture/s5_exec_01_edge_freeze.json"
GATE01_POLICY = ROOT / "docs/architecture/gate01_policy.json"
GATE01_ADJUDICATIONS = ROOT / "docs/architecture/gates/adjudications"
_GATE_SPEC = importlib.util.spec_from_file_location(
    "s5_gate01_authorization", Path(__file__).with_name("gate01_frozen_path_guard.py")
)
assert _GATE_SPEC is not None and _GATE_SPEC.loader is not None
GATE01 = importlib.util.module_from_spec(_GATE_SPEC)
_GATE_SPEC.loader.exec_module(GATE01)

# The owner's 2026-10-16 instruction permits only these reviewed U07 bytes. It does
# not permit SoR cutover. This finite binding measures that distinction; a label or
# free-form scope assertion cannot create another exception. Future bytes need a
# separate review. GATE-01 itself remains unchanged and still owns authorization.
_U07_ID = "GATE01-ADJ-2026-10-16-001"
_U07_BASELINE = "6ba0bef56f47926ce657515fe1717019522f868b"
_U07_DIGEST = "b4ef1787f9e75190ca2f7eb9d2a094559f7705fc29bc279436e4c429982b4665"
_U07_BLOBS = {
    "services/sahool-platform/api/phase_runtime_store.py": "b5f47f44efbdf9b8f34cd5d497f76a78077f1788",
    "migrations/MANIFEST.txt": "655fa0c89b1221af54b59d47c6f8f5d31bdd7d8f",
}


def _review_only_u07_authorization(doc: dict, policy: dict) -> bool:
    """Recognize only the reviewed non-cutover patch, then ask the real GATE validator."""
    bindings = doc.get("bindings") or {}
    baseline = doc.get("phase0_baseline_ref") or {}
    if (
        baseline.get("must_match_policy") is not True
        or any(
            bindings.get(key) is not True
            for key in ("require_patch_digest", "require_paths_subset", "require_baseline_match")
        )
        or bindings.get("require_exact_head_sha") is not False
        or doc.get("adjudication_id") != _U07_ID
        or doc.get("authorized_patch_sha256") != _U07_DIGEST
        or doc.get("authorized_blobs") != _U07_BLOBS
        or doc.get("allowed_paths") != list(_U07_BLOBS)
        or doc.get("allowed_gap_closures") != ["REPORT3-U07-REVIEW-DECISION-NOT-PERSISTED-01"]
        or doc.get("one_time") is not True
        or doc.get("adjudicated_on") != "2026-10-16"
        or doc.get("expires_on") != "2026-10-23"
        or doc.get("phase0_baseline_ref")
        != {"commit_sha": _U07_BASELINE, "must_match_policy": True}
        or doc.get("bindings")
        != {
            "require_patch_digest": True,
            "require_paths_subset": True,
            "require_baseline_match": True,
            "require_exact_head_sha": False,
        }
        or (policy.get("phase0_baseline") or {}).get("commit_sha") != _U07_BASELINE
        or (policy.get("gate") or {}).get("state") != "CLOSED"
        or not set(_U07_BLOBS).issubset(policy.get("frozen_paths") or [])
    ):
        return False
    actual = {path: GATE01.blob_sha(path, root=ROOT) for path in _U07_BLOBS}
    errors, used = GATE01.evaluate(list(_U07_BLOBS), policy, [doc], actual)
    return not errors and used == _U07_ID


# ── قطعٌ مؤجَّلٌ ببوّابة، لا متروك ────────────────────────────────────────────────
# الكاتب هنا مُجمَّد في FREEZE فيلزمه عقد قطع، لكنّ ملفّه **مسارٌ مجمَّد** في GATE-01
# وحالتها CLOSED بلا تفويضٍ ISSUED يجيز قطع الكاتب. فتنفيذ القطع الآن يخالف بوّابةً أخرى،
# وإصدارُ الإذن الذي تشترطه البوّابة — بيد المحجوب بها — يُبطِلها.
#
# والتأجيل **يُقاس ولا يُدَّعى**: `_gate01_blocks()` تقرأ السياسة والتفويضات وقت
# التشغيل، فإن فُتِحت البوّابة أو صدر تفويضٌ ISSUED غير رقعة U07 المحددة **سقط العذر فوراً**
# وعاد فرضُ العلامات. أي أنّه شرطٌ ينقضي بنفسه لا استثناءٌ دائم.
GATE01_DEFERRED: dict[tuple[str, str], str] = {
    (
        "services/sahool-platform/api/phase_runtime_store.py",
        "online_learning_updates",
    ): "GATE-01 CLOSED · لا إذن قطع؛ رقعة U07 المحددة بالبايتات لا تمنح إذن SoR",
}


def _gate01_blocks(writer: str) -> bool:
    """هل تمنع GATE-01 فعلاً تعديلَ هذا المسار الآن؟ (قياسٌ لا افتراض)"""
    if not GATE01_POLICY.is_file():
        return False
    policy = GATE01.load_policy(GATE01_POLICY)
    if writer not in set(policy.get("frozen_paths", [])):
        return False
    if str(policy.get("gate", {}).get("state", "")).upper() != "CLOSED":
        return False
    if GATE01_ADJUDICATIONS.is_dir():
        for adjudication in sorted(GATE01_ADJUDICATIONS.glob("*.json")):
            doc = json.loads(adjudication.read_text(encoding="utf-8"))
            if str(doc.get("status", "")).upper() == "ISSUED" and writer in (
                doc.get("allowed_paths") or []
            ):
                if _review_only_u07_authorization(doc, policy):
                    continue
                return False
    return True


# Contract markers are intentionally end-state semantics, not SQL discovery. The exact writer
# set comes from FREEZE; adding a writer there without adding a cutover contract blocks CI.
CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "services/sahool-platform/api/routers/recommendations.py": {
        "recommendation_outcomes": (
            "if mode.strict_decision_service_required:",
            '"authoritative_store": "decision-service"',
            'assert_platform_may_write_decision_sor("recommendation_outcomes")',
        ),
    },
    "services/sahool-platform/api/routers/decision_record.py": {
        "decision_record": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("decision_record")',
            '"authoritative_store": "decision-service"',
        ),
        "outcome_record": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("outcome_record")',
            '"authoritative_store": "decision-service"',
        ),
    },
    "services/sahool-platform/api/routers/weather.py": {
        "decision_record": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("decision_record")',
            "decision-service did not prove authoritative weather-decision persistence",
        ),
    },
    "services/sahool-platform/api/phase_runtime_store.py": {
        "online_learning_updates": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("online_learning_updates")',
            "decision-service did not prove authoritative learning-update persistence",
        ),
    },
    "services/sahool-platform/api/routers/decision_dispatch.py": {
        "dispatch_decisions": (
            "if mode.strict_decision_service_required:",
            "legacy_dispatch_writer_retired_after_decision_sor_cutover",
            'assert_platform_may_write_decision_sor("dispatch_decisions")',
        ),
    },
}


def _frozen_pairs() -> set[tuple[str, str]]:
    doc = json.loads(FREEZE.read_text(encoding="utf-8"))
    if doc.get("schema") != "sahool.s5-exec-01.edge-freeze/v2":
        raise RuntimeError("unexpected S5-EXEC-01 freeze schema")
    pairs: set[tuple[str, str]] = set()
    for item in doc.get("writer_cutover_set_runtime_only", []):
        table = str(item.get("table", ""))
        for writer in item.get("writers", []):
            pairs.add((str(writer), table))
    return pairs


def findings() -> list[str]:
    errors: list[str] = []
    frozen = _frozen_pairs()
    declared = {(path, table) for path, tables in CONTRACTS.items() for table in tables}
    missing_contract = sorted(frozen - declared)
    stale_contract = sorted(declared - frozen)
    for writer, table in missing_contract:
        errors.append(f"FROZEN_WRITER_WITHOUT_CUTOVER_CONTRACT {table} {writer}")
    for writer, table in stale_contract:
        errors.append(f"STALE_CUTOVER_CONTRACT {table} {writer}")

    for writer, table in sorted(frozen & declared):
        path = ROOT / writer
        if not path.is_file():
            errors.append(f"MISSING_FROZEN_WRITER {table} {writer}")
            continue
        if (writer, table) in GATE01_DEFERRED:
            if _gate01_blocks(writer):
                continue
            # البوّابة لم تعد تمنع ⇒ سقط العذر، فيُسمّى سقوطُه **ويُفرَض العقد** بعده.
            errors.append(f"GATE01_DEFERRAL_NO_LONGER_JUSTIFIED {table} {writer}")
        text = path.read_text(encoding="utf-8")
        for marker in CONTRACTS[writer][table]:
            if marker not in text:
                errors.append(f"CUTOVER_MARKER_MISSING {table} {writer}: {marker}")
    return errors


def deferred_pairs() -> list[tuple[str, str]]:
    """الأزواج المؤجَّلة **والمقيس** أنّ البوّابة ما زالت تمنعها."""
    return sorted(
        pair for pair in (_frozen_pairs() & set(GATE01_DEFERRED)) if _gate01_blocks(pair[0])
    )


def main() -> int:
    errors = findings()
    if errors:
        print("S5_EXEC_01_WRITER_CUTOVER_BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    # الأخضر لا يُخفي المؤجَّل: يُعلَن عدده واسمه، وإلّا قُرِئ «كلّ الكتّاب قُطِعوا».
    deferred = deferred_pairs()
    print(
        f"s5_exec_01_writer_cutover_ok frozen_writers={len(_frozen_pairs())} "
        f"gate01_deferred={len(deferred)}"
    )
    for writer, table in deferred:
        print(f"- DEFERRED_BY_GATE01 {table} {writer}: {GATE01_DEFERRED[(writer, table)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

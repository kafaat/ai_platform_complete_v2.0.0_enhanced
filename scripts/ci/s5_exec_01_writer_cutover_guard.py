#!/usr/bin/env python3
"""Fail closed unless every frozen S5-EXEC-01 platform writer has a single-authority end state.

The writer inventory comes exclusively from the generated edge-freeze artifact.  This guard
never re-derives edge_class or writer identity lexically.  It verifies the code-side cutover
contract for each frozen writer while the pre-cutover bridge remains physically present.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/architecture/s5_exec_01_edge_freeze.json"
GATE01_POLICY = ROOT / "docs/architecture/gate01_policy.json"
GATE01_ADJUDICATIONS = ROOT / "docs/architecture/gates/adjudications"

# ── قطعٌ مؤجَّلٌ ببوّابة، لا متروك ────────────────────────────────────────────────
# الكاتب هنا مُجمَّد في FREEZE فيلزمه عقد قطع، لكنّ ملفّه **مسارٌ مجمَّد** في GATE-01
# وحالتها CLOSED بلا تفويضٍ ISSUED يغطّيه. فتنفيذ القطع الآن يخالف بوّابةً أخرى،
# وإصدارُ الإذن الذي تشترطه البوّابة — بيد المحجوب بها — يُبطِلها.
#
# والتأجيل **يُقاس ولا يُدَّعى**: `_gate01_blocks()` تقرأ السياسة والتفويضات وقت
# التشغيل، فإن فُتِحت البوّابة أو صدر تفويضٌ ISSUED يغطّي المسار **سقط العذر فوراً**
# وعاد فرضُ العلامات. أي أنّه شرطٌ ينقضي بنفسه لا استثناءٌ دائم.
GATE01_DEFERRED: dict[tuple[str, str], str] = {
    (
        "services/sahool-platform/api/phase_runtime_store.py",
        "online_learning_updates",
    ): "GATE-01 CLOSED · لا تفويض ISSUED يغطّي هذا المسار المجمَّد",
}


def _gate01_blocks(writer: str) -> bool:
    """هل تمنع GATE-01 فعلاً تعديلَ هذا المسار الآن؟ (قياسٌ لا افتراض)"""
    if not GATE01_POLICY.is_file():
        return False
    policy = json.loads(GATE01_POLICY.read_text(encoding="utf-8"))
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

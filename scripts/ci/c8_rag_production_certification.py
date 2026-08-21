#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(rel, *args):
    p = subprocess.run(
        [sys.executable, str(ROOT / rel), *map(str, args)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.returncode, (p.stdout or "").strip()


def emit(stage, status, findings=(), **extra):
    o = {
        "schema": f"sahool.{stage.lower()}-certification/v2",
        "stage": stage,
        "status": status,
        "authority_changed": False,
        "findings": list(findings),
        **extra,
    }
    print(json.dumps(o, indent=2, sort_keys=True))
    return (
        0
        if status
        in {"PASS", "EVIDENCE_REQUIRED", "LIVE_PARITY_VERIFIED", "CERTIFIED_CUTOVER_CAPABLE"}
        else 1
    )


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--receipt")
    a.add_argument("--subject-sha")
    a.add_argument("--subject-tree")
    a.add_argument("--corpus-receipt")
    x = a.parse_args(argv)
    f = []
    for rel in (
        "scripts/architecture/rag_authority_convergence_guard.py",
        "scripts/architecture/rag_direct_qdrant_boundary_guard.py",
        "scripts/ci/rag_operational_boundary_guard.py",
    ):
        rc, out = run(rel)
        if rc:
            f.append(f"canonical_guard_failed:{rel}:{out[-500:]}")
    if f:
        return emit("C8", "FAILED", f)
    if not x.receipt:
        return emit("C8", "EVIDENCE_REQUIRED", ["live_rag_parity_receipt_missing"])
    if not x.subject_sha:
        return emit("C8", "FAILED", ["subject_sha_required_with_receipt"])
    rc, out = run(
        "scripts/architecture/rag_live_parity_receipt_guard.py",
        "--receipt",
        x.receipt,
        "--subject-sha",
        x.subject_sha,
    )
    if rc != 0:
        return emit(
            "C8",
            "FAILED",
            ["canonical_live_receipt_guard_failed", out[-800:]],
        )

    # A valid live receipt proves live parity and live **vector**-schema parity for
    # this observation. It does *not* mutate the adjudicated convergence state and
    # cannot make direct-Qdrant revocation ready by itself. Report cutover-capable
    # only when every remaining adjudicated requirement is already true.
    #
    # M0-C2: كان هنا `effective["collection_schema_parity"] = True` — اسمٌ واحد يحمل
    # حقيقتين، فيمنح تكافؤَ الـpayload خُضرةَ إيصالِ المتّجه. وهذا مسارُ شهادةٍ **ثانٍ**
    # موازٍ لحارس القبول ومحجوزٌ في `ci.yml`، فبقي العطلُ حيّاً فيه بعد أن فُصِل
    # الاسمان في الحارس و`/readyz`. والحسابُ كان قاطعاً: حارسُ تكافؤِ الـpayload
    # الوحيد هنا كان **مصادفةَ** بقاءِ `direct_qdrant_revocation_ready` كاذبةً —
    # ويومَ تُقلَب، وهي غايةُ البرنامج، تُصدَر `CERTIFIED_CUTOVER_CAPABLE` على إيصالٍ
    # أثبت تكافؤَ المتّجه وحده. أمسكه مراجعٌ آليّ على #882.
    #
    # **ولا تُرفَع `canonical_payload_parity` من إيصال المتّجه.** D08-C يجيز رفعها
    # فقط بعد تمرير إيصال جردٍ مستقلّ عبر الحارس القانوني نفسه الذي يستهلكه cutover.
    state = json.loads(
        (ROOT / "docs/architecture/rag_authority_convergence.json").read_text(encoding="utf-8")
    )
    effective = dict(state.get("cutover_requirements") or {})
    effective["collection_vector_schema_parity"] = True
    effective["live_shadow_parity_receipt"] = True

    # D08-C: the C8 wrapper consumes the same canonical corpus-receipt guard; it
    # does not define a second receipt language.  Absence of the receipt leaves
    # payload parity false.
    payload_parity_observed = False
    if x.corpus_receipt:
        if not x.subject_tree:
            return emit("C8", "FAILED", ["subject_tree_required_with_corpus_receipt"])
        rc, corpus_out = run(
            "scripts/architecture/rag_corpus_audit_receipt_guard.py",
            "--receipt",
            x.corpus_receipt,
            "--subject-sha",
            x.subject_sha,
            "--subject-tree",
            x.subject_tree,
        )
        if rc != 0:
            return emit(
                "C8",
                "FAILED",
                ["corpus_audit_receipt_invalid", corpus_out[-800:]],
            )
        corpus_receipt = json.loads(Path(x.corpus_receipt).read_text(encoding="utf-8"))
        payload_parity_observed = corpus_receipt.get("canonical_payload_parity") is True
    effective["canonical_payload_parity"] = payload_parity_observed
    blockers = sorted(key for key, value in effective.items() if not bool(value))
    status = "CERTIFIED_CUTOVER_CAPABLE" if not blockers else "LIVE_PARITY_VERIFIED"
    return emit(
        "C8",
        status,
        [],
        cutover_capable=not blockers,
        blocking_requirements=blockers,
        observed_requirements={
            "collection_vector_schema_parity": True,
            "live_shadow_parity_receipt": True,
            "canonical_payload_parity": bool(effective.get("canonical_payload_parity")),
            "corpus_audit_receipt_present": bool(x.corpus_receipt),
        },
        authority_state=state.get("authority_state"),
        convergence_stage=state.get("stage"),
    )


if __name__ == "__main__":
    raise SystemExit(main())

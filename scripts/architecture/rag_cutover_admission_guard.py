#!/usr/bin/env python3
"""Admission guard for a future RAG retrieval-authority cutover.

This tool does not mutate convergence state and does not promote authority.  It is
intended to be run *before* a cutover change.  Live parity is necessary but not
sufficient: the temporary direct response path must be revocable and the adjudicated
cutover requirements must all be satisfied.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "docs/architecture/rag_authority_convergence.json"


def _run(rel: str, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(ROOT / rel), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.returncode, (p.stdout or "").strip()


def _emit(status: str, findings: list[str], **extra: Any) -> int:
    print(
        json.dumps(
            {
                "schema": "sahool.rag-cutover-admission/v1",
                "status": status,
                "authority_changed": False,
                "findings": findings,
                **extra,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if status == "CUTOVER_ADMISSION_READY":
        return 0
    if status == "EVIDENCE_REQUIRED":
        return 2
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt")
    parser.add_argument("--subject-sha")
    args = parser.parse_args(argv)

    structural_findings: list[str] = []
    for rel in (
        "scripts/architecture/rag_authority_convergence_guard.py",
        "scripts/architecture/rag_direct_qdrant_boundary_guard.py",
        "scripts/ci/rag_operational_boundary_guard.py",
    ):
        rc, out = _run(rel)
        if rc:
            structural_findings.append(f"structural_guard_failed:{rel}:{out[-600:]}")
    if structural_findings:
        return _emit("FAILED", structural_findings, cutover_capable=False)

    if not args.receipt:
        return _emit(
            "EVIDENCE_REQUIRED",
            ["live_rag_parity_receipt_missing"],
            cutover_capable=False,
        )
    if not args.subject_sha:
        return _emit("FAILED", ["subject_sha_required_with_receipt"], cutover_capable=False)

    rc, out = _run(
        "scripts/architecture/rag_live_parity_receipt_guard.py",
        "--receipt",
        args.receipt,
        "--subject-sha",
        args.subject_sha,
    )
    if rc:
        return _emit(
            "FAILED",
            ["live_parity_receipt_invalid", out[-800:]],
            cutover_capable=False,
        )

    state = json.loads(STATE.read_text(encoding="utf-8"))
    requirements = dict(state.get("cutover_requirements") or {})
    # ── ما يُثبِته الإيصال، وما لا يُثبِته ────────────────────────────────────
    #
    # كان اسمٌ واحد `collection_schema_parity` يحمل حقيقتين: تطابقَ **مخطّط المتّجه**
    # وتطابقَ **مجموعة الـpayload**. والإيصال الحيّ يقيس الأولى وحدها — هويّةَ
    # المجموعة وبُعدَ المتّجه وهويّةَ النموذج — ولا يجرد payload كلّ نقطة.
    #
    # والشاهدُ الحيّ على الفرق قاطع: مخطّطُ المتّجه سليمٌ تماماً بينما ٥٤ نقطة غير
    # قابلة لإعادة البناء القانونيّة. فاسمٌ واحد كان يمنح الثانية خُضرةَ الأولى.
    requirements["collection_vector_schema_parity"] = True
    requirements["live_shadow_parity_receipt"] = True
    # **ولا تُرفَع من هنا.** تكافؤُ الـpayload يحتاج جردَ مجموعةٍ فعليّاً: عدٌّ دقيق
    # مطابقٌ للمسح · وكلُّ نقطةٍ مصنّفة · وصفرُ غيرِ مصنّف. ولا يكفي `skipped == 0`
    # ما دام المحلّل يقبل ارتداداتٍ قديمة تجعل نقطةً مرئيّةً للمتناثر دون الكثيف.
    # فتبقى `False` حتّى يوجد إيصالُ جردٍ يقولها — لا تُلفَّق من فحصٍ ساكن.
    # **إسنادٌ صريح لا `setdefault`.** الأخير كان يُبقي أيَّ `True` سابقة في وثيقة
    # الحالة — ولا يتحقّق هذا الحارس من أيّ إيصال جرد، فتصير علامةٌ بائتةٌ أو مكتوبةٌ
    # يدويّاً كافيةً لإخضار تكافؤ الـpayload بعد إيصال المتّجه وحده. أمسكه مراجعٌ
    # آليّ على #882، وهو صنفُ العطل الذي تُصنّفه هذه الشريحة بعينه.
    requirements["canonical_payload_parity"] = False
    blockers = sorted(key for key, value in requirements.items() if not bool(value))

    # A named pre-cutover direct response exception is explicit evidence that revocation
    # has not happened yet.  Do not infer readiness from a receipt alone.
    exception = (state.get("direct_qdrant_exception") or {}).get("component_id")
    if exception:
        blockers.append(f"direct_response_path_exception_present:{exception}")

    blockers = sorted(set(blockers))
    if blockers:
        return _emit(
            "BLOCKED",
            ["cutover_requirements_incomplete"],
            cutover_capable=False,
            blocking_requirements=blockers,
            convergence_stage=state.get("stage"),
            authority_state=state.get("authority_state"),
            observed_requirements={
                "collection_vector_schema_parity": True,
                "live_shadow_parity_receipt": True,
                "canonical_payload_parity": bool(requirements.get("canonical_payload_parity")),
            },
        )

    return _emit(
        "CUTOVER_ADMISSION_READY",
        [],
        cutover_capable=True,
        blocking_requirements=[],
        convergence_stage=state.get("stage"),
        authority_state=state.get("authority_state"),
        observed_requirements={
            "collection_vector_schema_parity": True,
            "live_shadow_parity_receipt": True,
            "canonical_payload_parity": bool(requirements.get("canonical_payload_parity")),
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())

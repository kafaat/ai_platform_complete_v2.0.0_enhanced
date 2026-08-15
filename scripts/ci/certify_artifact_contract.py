#!/usr/bin/env python3
"""عقدُ مصنوعة الاعتماد: اسمٌ مشتقٌّ من ``head_sha``، وexactly-one، وهويّةٌ تُسجَّل.

**العطل الذي وُجِد لأجله مقيسٌ لا مُفترَض:** ``ci.yml`` ترفع الدليل باسم
``live-pg-evidence-<sha>`` بينما كانت وظيفةُ الاعتماد تُنزِّل الاسم الثابت
``live-pg-evidence`` — فيفشل التنزيل **في كلّ تشغيل**، ويُقرأ الفشلُ «لا دليل في
هذا التشغيل»، فلا يُنتَج سجلُّ اعتمادٍ قطّ. غيابٌ بنيويٌّ ارتدى ثوبَ غيابٍ مشروع.

فالاسم هنا **يُشتقّ ولا يُبحَث**: يُبنى من ``head_sha`` المشهود له حرفاً حرفاً، بلا
wildcard ولا أحدث-ما-وُجِد — لأنّ البحث يلتقط أقربَ شبيهٍ، والاشتقاق يلتقط
المقصودَ أو لا شيء. ويُفرَض **exactly-one**: صفرٌ للدليل غيابٌ مشروعٌ يُعلَن باسمه؛
والتكرارُ التباسُ هويّةٍ يُرفَض لا يُفَضّ بالاختيار. وتُسجَّل هويّةُ كلّ مصنوعة
(``artifact_id`` + ``digest``) ليقدر المدقّق لاحقاً على تسمية **أيّ بايتات** حُكِم
عليها — لا «مصنوعةٍ ما بهذا الاسم يومها».

**وحدُّ صدقه:** يقرأ جردَ المصنوعات كما جلبته الوظيفة ويحكم على شكله؛ التنزيلُ
الفعليّ يجري في الـworkflow بمعرّف المصنوعة المُسجَّل هنا، وسلامةُ البايتات تُثبَت
بعده بما هو أقوى من بصمة النقل: مطابقةُ البيان الموقَّع والتحقّقُ التشفيريّ من
الحزمة في ``sot_provenance_guard``. (``scripts/ci/**`` لا يستدعي GitHub في هذا
المستودع — يحرسه عقدُ ``test_local_preflight_contract``.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجٌ عربيّ يُرمَّز بلغة الآلة.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SCHEMA = "sahool.certify-artifact-contract/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")

#: المصنوعتان المطلوبتان لاعتماد لقطة — والاسم دالّةٌ في الـSHA لا نصٌّ ثابت.
ROLES = {
    "evidence": "live-pg-evidence-{sha}",
    "attestation": "live-pg-evidence-attestation-{sha}",
}


def _load(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"✗ تعذّرت قراءة جرد المصنوعات {path}: {exc}") from None
    if not isinstance(document, dict) or not isinstance(document.get("artifacts"), list):
        raise SystemExit("✗ جردُ المصنوعات ليس بالشكل المتعاقَد عليه — «لم يُقرأ» ليس «فارغ».")
    return document


def judge(inventory: dict, head_sha: str) -> dict:
    """الحكم: ``absent`` غيابٌ مشروعٌ مُعلَن، و``present`` هويّتان مُسجَّلتان — وما
    بينهما (تكرار، دليلٌ بلا إثبات منشأ، إثباتٌ بلا دليل، منتهي الصلاحية) يُرفَض."""
    if not SHA40.fullmatch(head_sha):
        raise SystemExit("✗ head_sha ليس SHA كاملاً — اسمٌ مشتقٌّ من التباسٍ يلتقط التباساً.")
    matches: dict[str, list[dict]] = {role: [] for role in ROLES}
    for artifact in inventory["artifacts"]:
        if not isinstance(artifact, dict):
            continue
        for role, pattern in ROLES.items():
            if artifact.get("name") == pattern.format(sha=head_sha):
                matches[role].append(artifact)
    problems: list[str] = []
    for role, found in matches.items():
        if len(found) > 1:
            problems.append(f"AMBIGUOUS_ARTIFACT:{role}:{len(found)}")
        for artifact in found:
            if artifact.get("expired") is True:
                # مصنوعةٌ منتهية ليست غائبة: الاسم يَعِد بمحتوىً لم يعد يُنال،
                # والحكم عليها «حاضرة» يكذب وعليها «غائبة» يطمس أنّها وُجِدت.
                problems.append(f"EXPIRED_ARTIFACT:{role}")
            run = artifact.get("workflow_run")
            if isinstance(run, dict) and run.get("head_sha") not in (None, head_sha):
                # اسمٌ مطابق من تشغيلٍ عن لقطةٍ أخرى — الاسم ادّعاءٌ والهويّة تُقاس.
                problems.append(f"FOREIGN_SUBJECT_ARTIFACT:{role}")
    if not matches["evidence"] and matches["attestation"]:
        problems.append("ATTESTATION_WITHOUT_EVIDENCE")
    if matches["evidence"] and not matches["attestation"]:
        # دليلٌ بلا حزمة توقيعٍ مرفوعة على `main` عطلٌ لا حالة: خطوةُ التوقيع في
        # `ci.yml` حاجزةٌ بمحاولتين، فغيابُ مصنوعتها هنا يعني تشغيلاً مكسوراً.
        problems.append("EVIDENCE_WITHOUT_ATTESTATION")
    if problems:
        raise SystemExit("✗ عقد المصنوعة مرفوض:\n  - " + "\n  - ".join(sorted(set(problems))))
    if not matches["evidence"]:
        return {"schema": SCHEMA, "head_sha": head_sha, "status": "absent", "artifacts": None}
    recorded = {}
    for role, found in matches.items():
        artifact = found[0]
        artifact_id = artifact.get("id")
        digest = artifact.get("digest")
        if not isinstance(artifact_id, int) or not isinstance(digest, str) or not digest:
            # هويّةٌ لا تُسمّى لا تُسجَّل ادّعاءً: بلا id/digest لا يستطيع مدقّقٌ
            # لاحقٌ تسمية البايتات المحكوم عليها — فيُرفَض لا يُدوَّن ناقصاً.
            raise SystemExit(f"✗ مصنوعة {role} بلا artifact_id/digest — هويّةٌ لا تُسمّى.")
        recorded[role] = {
            "name": artifact["name"],
            "artifact_id": artifact_id,
            "digest": digest,
            "size_in_bytes": artifact.get("size_in_bytes"),
        }
    return {
        "schema": SCHEMA,
        "head_sha": head_sha,
        "status": "present",
        "artifacts": recorded,
        "$honesty_limit_ar": (
            "يحكم على جرد المصنوعات كما أعلنته الواجهة: الاسم مشتقٌّ من head_sha "
            "وexactly-one مفروض والهويّة مُسجَّلة. سلامةُ البايتات المنزَّلة تُثبَت "
            "لاحقاً بالبيان الموقَّع والتحقّق التشفيريّ، لا ببصمة النقل وحدها."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="عقد مصنوعة الاعتماد المشتقّ من head_sha")
    ap.add_argument("--artifacts-file", type=Path, required=True)
    ap.add_argument("--head-sha", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    verdict = judge(_load(args.artifacts_file), args.head_sha)
    args.output.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if verdict["status"] == "absent":
        print("certify_artifact_contract: absent — لا حزمة أدلّة لهذه اللقطة، والغياب يُعلَن باسمه")
    else:
        ids = {role: entry["artifact_id"] for role, entry in verdict["artifacts"].items()}
        print(f"certify_artifact_contract: present — exactly-one لكلّ دور: {ids}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

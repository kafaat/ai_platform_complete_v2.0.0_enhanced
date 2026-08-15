"""عقدُ مصنوعة الاعتماد — الاسم يُشتقّ من ``head_sha`` ولا يُبحَث.

الواقعة المؤسِّسة مقيسة: ``ci.yml`` ترفع ``live-pg-evidence-<sha>`` وكانت وظيفةُ
الاعتماد تُنزِّل الاسم الثابت ``live-pg-evidence`` — فيفشل التنزيل في **كلّ**
تشغيل ويُقرأ «لا دليل في هذا التشغيل»، فلا يُنتَج سجلُّ اعتمادٍ قطّ. غيابٌ
بنيويٌّ ارتدى ثوبَ غيابٍ مشروع، وكشفه المالك بالقياس لا بالمصادفة.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "certify_artifact_contract", ROOT / "scripts/ci/certify_artifact_contract.py"
)
probe = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(probe)

HEAD = "a7215385de59c4fc27f6723226e2fe737770cd4d"


def _artifact(name: str, **over) -> dict:
    base = {
        "id": 40374289,
        "name": name,
        "digest": "sha256:" + "a" * 64,
        "size_in_bytes": 12345,
        "expired": False,
        "workflow_run": {"head_sha": HEAD},
    }
    base.update(over)
    return base


def _inventory(*artifacts) -> dict:
    return {"artifacts": list(artifacts)}


def _pair() -> tuple[dict, dict]:
    return (
        _artifact(f"live-pg-evidence-{HEAD}"),
        _artifact(f"live-pg-evidence-attestation-{HEAD}", id=40374290),
    )


def test_exactly_one_of_each_role_is_present_with_recorded_identity() -> None:
    """البند الموجب: هويّتا المصنوعتين (artifact_id + digest) تُسجَّلان للمدقّق."""
    verdict = probe.judge(_inventory(*_pair()), HEAD)

    assert verdict["status"] == "present"
    assert verdict["artifacts"]["evidence"]["artifact_id"] == 40374289
    assert verdict["artifacts"]["attestation"]["artifact_id"] == 40374290
    assert verdict["artifacts"]["evidence"]["digest"].startswith("sha256:")


def test_no_evidence_at_all_is_a_declared_absence_not_a_failure() -> None:
    """تشغيلٌ لم يبلغ وظيفة الأدلّة لا شيء فيه ليُعتمَد — ويُقال ذلك باسمه."""
    verdict = probe.judge(_inventory(_artifact("some-other-artifact")), HEAD)

    assert verdict == {
        "schema": probe.SCHEMA,
        "head_sha": HEAD,
        "status": "absent",
        "artifacts": None,
    }


def test_the_fixed_legacy_name_is_not_matched_by_derivation() -> None:
    """الاسم الثابت القديم `live-pg-evidence` لا يطابق الاسم المشتقّ — وهو العطل عينه."""
    verdict = probe.judge(
        _inventory(_artifact("live-pg-evidence"), _artifact("live-pg-evidence-abc123")), HEAD
    )

    assert verdict["status"] == "absent"


def test_duplicate_evidence_artifacts_are_refused_not_disambiguated() -> None:
    """التكرار التباسُ هويّة يُرفَض — لا يُفَضّ باختيار الأحدث."""
    ev, at = _pair()
    with pytest.raises(SystemExit, match="AMBIGUOUS_ARTIFACT:evidence:2"):
        probe.judge(_inventory(ev, dict(ev), at), HEAD)


def test_evidence_without_its_attestation_is_a_violation_not_an_absence() -> None:
    """خطوة التوقيع في `ci.yml` حاجزة بمحاولتين — فغياب مصنوعتها هنا تشغيلٌ مكسور."""
    ev, _ = _pair()
    with pytest.raises(SystemExit, match="EVIDENCE_WITHOUT_ATTESTATION"):
        probe.judge(_inventory(ev), HEAD)


def test_an_attestation_without_its_evidence_is_a_violation() -> None:
    _, at = _pair()
    with pytest.raises(SystemExit, match="ATTESTATION_WITHOUT_EVIDENCE"):
        probe.judge(_inventory(at), HEAD)


def test_an_expired_artifact_is_named_expired_not_read_as_present_or_absent() -> None:
    ev, at = _pair()
    with pytest.raises(SystemExit, match="EXPIRED_ARTIFACT:evidence"):
        probe.judge(_inventory(_artifact(ev["name"], expired=True), at), HEAD)


def test_a_matching_name_from_a_foreign_head_is_refused() -> None:
    """الاسم ادّعاءٌ والهويّة تُقاس: مصنوعةٌ باسمٍ مطابق من تشغيلٍ عن لقطةٍ أخرى تُرفَض."""
    ev, at = _pair()
    foreign = _artifact(ev["name"], workflow_run={"head_sha": "0" * 40})
    with pytest.raises(SystemExit, match="FOREIGN_SUBJECT_ARTIFACT:evidence"):
        probe.judge(_inventory(foreign, at), HEAD)


def test_an_artifact_without_a_recordable_identity_is_refused() -> None:
    """بلا artifact_id/digest لا يستطيع مدقّقٌ لاحق تسمية البايتات المحكوم عليها."""
    ev, at = _pair()
    with pytest.raises(SystemExit, match="هويّةٌ لا تُسمّى"):
        probe.judge(_inventory(_artifact(ev["name"], digest=None), at), HEAD)


def test_a_short_or_malformed_head_sha_is_refused_before_any_matching() -> None:
    """اسمٌ مشتقٌّ من التباسٍ يلتقط التباساً — فيُرفَض المدخل قبل المطابقة."""
    with pytest.raises(SystemExit, match="SHA"):
        probe.judge(_inventory(*_pair()), "a7215385")


def test_a_malformed_inventory_is_refused_not_read_as_empty(tmp_path) -> None:
    """«لم يُقرأ» ليس «فارغ» — جردٌ بلا شكله المتعاقَد يُرفَض."""
    p = tmp_path / "artifacts.json"
    p.write_text('{"artifacts": "not-a-list"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="المتعاقَد"):
        probe._load(p)


def test_the_cli_writes_the_verdict_document(tmp_path) -> None:
    inventory = tmp_path / "artifacts.json"
    inventory.write_text(json.dumps(_inventory(*_pair())), encoding="utf-8")
    out = tmp_path / "artifact_contract.json"

    assert (
        probe.main(["--artifacts-file", str(inventory), "--head-sha", HEAD, "--output", str(out)])
        == 0
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["status"] == "present"
    assert doc["schema"] == "sahool.certify-artifact-contract/v1"

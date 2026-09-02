"""PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01 — نصفُه الأوّل.

**العطلُ مُكذَّبٌ بالتنفيذ قبل أن يُكتَب سطرُ علاج:** في رملٍ معزول أنتجت **أربعةُ
ملفّات JSON مكتوبةٍ باليد** `production_certified=true` وخروجاً `0` — ببصمةٍ من
**أربعين صفراً**، و`repository: attacker/x`، وقوائمَ فارغة، وقيمِ `null`، وإعفاءٍ
**بلا حقل سببٍ أصلاً**. والكلمةُ «سبب» كانت في **اسم الحالة**
(`waived_with_reason`) لا في البيانات — فالإعفاءُ اسمُه شرطُه.

**والعلّةُ البنيويّة أنّ الحكمَ لم يكن حيث الصرامة:** `production_evidence_pack_guard`
يفرض provenance وشكلَ بصمةٍ وطزاجةَ ختم، و`production_certification_blockers_status`
**لا يستدعيه قطّ** — بل يقارن `row["status"] == "verified"` نصّاً. وقائمتاهما
اختلفتا: أربعةُ حواجزَ هنا وخمسةٌ هناك، فالحاجبُ الخامس (`GUARDS`) **لم يكن
يُقيَّم أصلاً** لا لأنّه غيرُ معرَّفٍ بل لأنّ القائمتين لم تتّفقا.

وهذا الملفّ يقيس الاتّجاهين معاً — وهو شرطُ ألّا يصير الحارسُ إزعاجاً يُلتَفّ
عليه: **الدليلُ الصالحُ يُعتمَد**، والمُختلَقُ يُرفَض **بسببه الصحيح**.

**وتصحيحٌ يُسجَّل من بناء هذا الملفّ نفسِه:** أوّلُ مِسبارٍ لي رفض الدليلَ الصالح،
فظننتُ الحارسَ يُحمِّر على الصواب — والعلّةُ كانت في المِسبار: كتبتُ الأدلّةَ
**بعد** توليد البيان فانحرف. فالبيانُ يُعاد توليدُه بعد الكتابة هنا. ولولا قياسُ
الحالة السويّة لَما ظهر ذلك، ولَبقي حارسٌ يبدو صارماً وهو معطَّل.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD_SRC = ROOT / "scripts" / "ci" / "production_evidence_pack_guard.py"
ADJUDICATOR_SRC = ROOT / "scripts" / "ci" / "production_certification_blockers_status.py"

REPO = "kafaat/ai_platform_complete_v2.0.0_enhanced"
_BASE = {
    "repository": REPO,
    "workflow": "CI",
    "workflow_run_id": "1",
    "commit": "a" * 39 + "b",
    "timestamp_utc": "2026-09-02T00:00:00+00:00",
}
#: كلُّ الحقول الدنيا لكلّ الحواجز — قيمٌ ذاتُ مضمون، لا مفاتيحُ حاضرة.
_FIELDS = {
    f: ["x"]
    for f in (
        "branch",
        "jobs",
        "command",
        "index_url_policy",
        "lock_files",
        "edge_readiness_mode",
        "edge_production_required",
        "artifacts",
        "guards",
        "redis_url_kind",
        "test_command",
        "readyz_cache_backend",
    )
}
_FILES = (
    "ci_summary.json",
    "transitive_locks_summary.json",
    "model_provisioning_summary.json",
    "guard_results_summary.json",
    "redis_live_test_summary.json",
)
_VALID_WAIVER = {
    "status": "waived_with_reason",
    "reason": "Redis is not used for correctness or state in the target deployment",
    "owner": "platform",
    "scope": "P-CERT-3",
    "expiry": "2027-01-01",
    "approver": "security",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _adjudicate(*, patch=None, target=None, env=None, waiver=None) -> dict:
    """يُشغّل الحكمَ على دليلٍ مُصطنَعٍ في **رملٍ معزول** — لا تُمَسّ أدلّةُ المستودع."""
    sandbox = Path(tempfile.mkdtemp()) / "evidence"
    sandbox.mkdir(parents=True)

    guard = _load("_guard_under_test", GUARD_SRC)
    guard.EVIDENCE_DIR = sandbox
    guard.MANIFEST = sandbox / "production_evidence_manifest.generated.json"
    guard.write_files()

    for name in _FILES:
        body = {**_BASE, **_FIELDS, "status": "verified"}
        if waiver is not None and name == "redis_live_test_summary.json":
            body = {**_BASE, **waiver}
        if patch is not None and name == target:
            body = {**body, **patch}
        (sandbox / name).write_text(json.dumps(body), encoding="utf-8")

    # البيانُ يُعاد توليدُه **بعد** كتابة الأدلّة — وإلّا كان الانحرافُ من المِسبار.
    guard.MANIFEST.write_text(
        json.dumps(guard.manifest_payload(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    adjudicator = _load("_adjudicator_under_test", ADJUDICATOR_SRC)
    adjudicator.EVIDENCE_DIR = sandbox
    adjudicator._evidence_guard = lambda: guard

    previous = dict(os.environ)
    if env:
        os.environ.update(env)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            adjudicator.main(require_certified=True)
        return json.loads(buf.getvalue())
    finally:
        os.environ.clear()
        os.environ.update(previous)


# ── ① الحالتان السويّتان — بلا هذا يصير الحارسُ إزعاجاً يُلتَفّ عليه ──────
def test_complete_and_valid_evidence_is_certified():
    """حارسٌ لا يمرّ على الصواب هو «المسارُ الشرعيُّ لا يستطيع النجاح» بعينه."""
    out = _adjudicate()
    assert out["evidence_pack_error"] is None, out["evidence_pack_error"]
    assert out["production_certified"] is True


def test_a_waiver_carrying_all_five_conditions_is_accepted():
    out = _adjudicate(waiver=_VALID_WAIVER)
    assert out["production_certified"] is True, out["evidence_pack_error"]


# ── ② الحكمُ يقرأ القائمةَ الواحدة، لا قائمةً ثانية ──────────────────────
def test_the_adjudicator_evaluates_every_blocker_the_strict_guard_declares():
    """القائمتان كانتا أربعةً وخمسة — فالحاجبُ الخامس لم يكن يُقيَّم أصلاً."""
    guard = _load("_guard_for_ids", GUARD_SRC)
    declared = {item["id"] for item in guard.BLOCKERS}
    adjudicated = {row["blocker_id"] for row in _adjudicate()["blockers"]}
    assert adjudicated == declared
    assert "GUARDS" in adjudicated, "الحاجبُ الخامس غائبٌ عن الحكم"


# ── ③ اتّجاهُ الخداع: كلُّ فحصٍ معزولٌ وكلُّ ما عداه صالح ─────────────────
@pytest.mark.parametrize(
    ("case", "target", "patch", "env", "waiver", "expected"),
    [
        (
            "بصمةٌ منحلّة",
            "transitive_locks_summary.json",
            {"commit": "0" * 40},
            None,
            None,
            "degenerate",
        ),
        (
            "مستودعٌ لا يطابق",
            "ci_summary.json",
            {"repository": "attacker/x"},
            {"GITHUB_REPOSITORY": REPO},
            None,
            "does not match",
        ),
        (
            "workflow لا يطابق",
            "ci_summary.json",
            {"workflow": "Other"},
            {"GITHUB_WORKFLOW": "CI"},
            None,
            "does not match",
        ),
        (
            "قائمةٌ فارغة",
            "model_provisioning_summary.json",
            {"artifacts": []},
            None,
            None,
            "missing/empty fields",
        ),
        (
            "قيمة null",
            "guard_results_summary.json",
            {"guards": None},
            None,
            None,
            "missing/empty fields",
        ),
        (
            "إعفاءٌ بلا موافق",
            None,
            None,
            None,
            {k: v for k, v in _VALID_WAIVER.items() if k != "approver"},
            "approver",
        ),
        (
            "موافقٌ = المالك",
            None,
            None,
            None,
            {**_VALID_WAIVER, "approver": "platform"},
            "must differ from owner",
        ),
        ("إعفاءٌ منقضٍ", None, None, None, {**_VALID_WAIVER, "expiry": "2020-01-01"}, "expired"),
    ],
)
def test_forged_evidence_is_refused_for_its_own_reason(case, target, patch, env, waiver, expected):
    """**والسببُ يُقاس لا الرفضُ وحدَه.**

    أوّلُ تشغيلٍ لهذه الحالات رفضها جميعاً — لكن بفحصٍ **قديم** سابقٍ على فحوصي
    (`timestamp_utc` مفقود)، فمرّ الاختبارُ ولم يقِس ما يدّعيه. فصار كلُّ حالةٍ
    صالحةً في كلّ شيءٍ إلّا عيبَها، ويُطابَق **نصُّ السبب**.
    """
    out = _adjudicate(patch=patch, target=target, env=env, waiver=waiver)
    assert out["production_certified"] is False, f"{case}: دليلٌ مُختلَقٌ اعتُمِد"
    assert expected in (out["evidence_pack_error"] or ""), (
        f"{case}: رُفِض بسببٍ غير المقصود — {out['evidence_pack_error']}"
    )

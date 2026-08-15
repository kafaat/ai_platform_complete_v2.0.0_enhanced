from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_certification_gate_is_fail_closed():
    data = json.loads(
        (ROOT / "runtime-verification/generated/runtime_certification_summary.json").read_text()
    )
    assert data["fail_closed"] is True
    assert data["gate_passed"] is True
    assert data["production_certified_services"] == []


def test_no_capability_or_service_claim_violations():
    data = json.loads(
        (ROOT / "runtime-verification/generated/runtime_certification_summary.json").read_text()
    )
    assert data["service_claim_violations"] == []
    assert data["capability_claim_violations"] == []


# ── استهلاك سجلّ الاعتماد: مؤشّرٌ لا برهان، ولا مُدقِّق ثانٍ ──────────────────

_SPEC = _ilu.spec_from_file_location(
    "runtime_certification_gate", ROOT / "scripts/ci/runtime_certification_gate.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_GATE = _ilu.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GATE)

_LIVE_HEAD = "2d8fdb3f2e34b5ecd8cc9cafda4df4d0309fc1a3"


def test_the_shipped_acceptance_record_loads_with_its_full_identity():
    """أوّل سجلّ اعتماد حيّ (التشغيل 31907504319) مقبولٌ بهويّته الكاملة لا باسمه.

    «الكاملة» تعني كتلة القبول كما هي بلا إسقاط — مراجعةٌ آليّة أصابت في أنّ
    محمّلاً يُرجِع subset باسم الهويّة الكاملة عقدٌ غامض، فصار المحمّل يتحقّق من
    كلّ حقلٍ ثم يحمل الكتلة كاملةً، وهذا الاختبار يقيسها حقلاً حقلاً."""
    accepted = _GATE.load_certification_acceptance()

    assert accepted is not None
    assert accepted["head_sha"] == _LIVE_HEAD
    assert accepted["tree_sha"] == "d7138dff67b1a6a8523be872c3a60c1f4fa10bc6"
    assert accepted["verdict"] == "VERIFIED"
    assert accepted["assurance_level"] == "L5"
    assert accepted["reason_codes"] == []
    assert accepted["producer_run_id"] == "31905594023"
    assert accepted["producer_run_attempt"] == "1"
    assert accepted["certify_run_id"] == "31907504319"
    assert accepted["certification_record_artifact"]["artifact_id"] == 9252747952
    assert accepted["execution_outcome_artifact"]["artifact_id"] == 9252747720
    assert len(accepted["manifest_sha256"]) == 64
    assert accepted["recorded_at"] == "2026-08-15T20:44:37Z"
    # والكتلة المحمولة هي كتلة الملفّ نفسها — لا subset يعيد صياغتها:
    shipped = json.loads(
        (ROOT / "docs/architecture/certification_acceptance_record.json").read_text(
            encoding="utf-8"
        )
    )
    assert accepted == shipped["accepted"]


def test_a_missing_acceptance_file_reads_as_no_acceptance_not_as_error(tmp_path):
    """غيابُ الملفّ غيابُ قبولٍ يُعلَن None — لا عطلٌ ولا قبولٌ مُفترَض."""
    assert _GATE.load_certification_acceptance(tmp_path / "absent.json") is None


def test_a_corrupt_acceptance_file_breaks_loudly_not_swallowed(tmp_path):
    """ابتلاعُ ملفٍّ لا يُقرأ كان يصنع قبولاً كاذباً — الفساد يكسر بصوت."""
    import json as _json

    import pytest as _pytest

    broken = tmp_path / "acceptance.json"
    broken.write_text("{not json", encoding="utf-8")
    with _pytest.raises(_json.JSONDecodeError):
        _GATE.load_certification_acceptance(broken)

    unsigned = tmp_path / "unsigned.json"
    unsigned.write_text('{"schema": "something.else/v9"}', encoding="utf-8")
    with _pytest.raises(ValueError, match="schema"):
        _GATE.load_certification_acceptance(unsigned)


def test_an_acceptance_without_artifact_identity_is_refused(tmp_path):
    """قبولٌ بلا artifact_id/digest لا يستطيع مدقّقٌ لاحق تسمية بايتاته — يُرفَض."""
    import json as _json

    import pytest as _pytest

    doc = _json.loads(
        (ROOT / "docs/architecture/certification_acceptance_record.json").read_text(
            encoding="utf-8"
        )
    )
    del doc["accepted"]["certification_record_artifact"]["digest"]
    p = tmp_path / "acceptance.json"
    p.write_text(_json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with _pytest.raises(ValueError, match="digest"):
        _GATE.load_certification_acceptance(p)


def test_a_malformed_digest_is_refused_not_carried_as_a_misleading_reference(tmp_path):
    """بصمةٌ «غير فارغة» لا تكفي: صيغة المستودع الصارمة `sha256:` + 64 hex —
    بصمةٌ مُضلِّلة الشكل مرجعٌ لا يقود إلى شيء (رفعته مراجعة آليّة وأصابت)."""
    import json as _json

    import pytest as _pytest

    doc = _json.loads(
        (ROOT / "docs/architecture/certification_acceptance_record.json").read_text(
            encoding="utf-8"
        )
    )
    doc["accepted"]["execution_outcome_artifact"]["digest"] = "sha256:short"
    p = tmp_path / "acceptance.json"
    p.write_text(_json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with _pytest.raises(ValueError, match="digest malformed"):
        _GATE.load_certification_acceptance(p)

    doc["accepted"]["execution_outcome_artifact"]["digest"] = "not-a-digest-at-all"
    p.write_text(_json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with _pytest.raises(ValueError, match="digest malformed"):
        _GATE.load_certification_acceptance(p)


def test_the_summary_carries_the_acceptance_and_never_judges_with_it():
    """المرجع يُحمَل كما هو، والحكم لا يتغيّر به: البوّابة والمخالفات وشروط
    الترقية كلّها من مصادرها الأصليّة — production_certified يبقى قراراً خارجيّاً.

    **ويُبنى الملخّص طازجاً لا يُقرأ من مصنوعةٍ مولَّدة سلفاً:** أوّل صياغةٍ قرأت
    الملفّ المولَّد فبقيت خضراء على العطل المزروع — أمسكها `guard_mutation_guard`
    («الاختبار يقرأ مصنوعةً مُولَّدة سلفاً بدل أن يمرّ بالقاعدة نفسها»)."""
    summary, _report = _GATE.build()

    assert summary["certification_acceptance"] == _GATE.load_certification_acceptance()
    # ولو كان المرجع L5 فالقرارات لا تتحرّك به:
    assert summary["production_certified_services"] == []
    assert all(c["production_certified_claim"] is False for c in summary["capabilities"])
    # والمصنوعة المولَّدة المشحونة تطابق البناء الطازج — لا انحراف بين القاعدة وأثرها:
    data = json.loads(
        (ROOT / "runtime-verification/generated/runtime_certification_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["certification_acceptance"] == summary["certification_acceptance"]


def test_the_capability_certification_gate_surfaces_the_same_reference_without_granting():
    """المستهلك الثاني يعرض المرجع نفسه ولا يمنح به أهليّة.

    البوّابة تُشغَّل فعلاً (مخرجاتها متقاربة idempotent على شجرةٍ سليمة) كي تمرّ
    القاعدةُ نفسها لا مصنوعتُها المولَّدة سلفاً — درس الطفرة أعلاه نفسه."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/capability_certification_gate.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(
        (ROOT / "capabilities/generated/capability_certification_summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert summary["release_assurance_reference"] == _GATE.load_certification_acceptance()
    assert summary["certified"] == 0
    assert summary["incorrect_certifications"] == []

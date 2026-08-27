from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/staging/s5_live_authority_closure.py"
spec = importlib.util.spec_from_file_location("s5_live_authority_closure", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

SHA = "a" * 40


def _receipt(path: Path, schema: str, *, sha: str = SHA, promotion: bool = False) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": schema,
                "subject_sha": sha,
                "authority_promotion": promotion,
                "observed_at": "2026-08-18T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _paths(tmp_path: Path):
    d = tmp_path / "decision.json"
    f = tmp_path / "field.json"
    k = tmp_path / "kg.json"
    _receipt(d, mod.RECEIPTS["decision"]["receipt_schema"])
    _receipt(f, mod.RECEIPTS["field_management"]["receipt_schema"])
    _receipt(k, mod.RECEIPTS["knowledge_graph"]["receipt_schema"])
    return d, f, k


def test_three_canonical_guards_are_required_before_adjudication(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "PASSED"
    assert body["live_evidence_complete"] is True
    assert body["ready_for_authority_adjudication"] is True
    assert body["authority_promotion"] is False
    assert body["physical_shrink_authorized"] is False


def test_one_failed_domain_guard_blocks_the_whole_bundle(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)

    def fake_guard(path, **kwargs):
        ok = path != f
        return {"passed": ok, "returncode": 0 if ok else 1, "output": "ok" if ok else "bad"}

    monkeypatch.setattr(mod, "_guard", fake_guard)
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert body["ready_for_authority_adjudication"] is False
    assert "field_management:canonical_guard_failed" in body["findings"]


def test_cross_subject_receipt_is_rejected_even_if_guard_is_stubbed_green(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    _receipt(k, mod.RECEIPTS["knowledge_graph"]["receipt_schema"], sha="b" * 40)
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert "knowledge_graph:subject_sha_mismatch" in body["findings"]


def test_receipt_that_claims_authority_promotion_is_rejected(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    _receipt(d, mod.RECEIPTS["decision"]["receipt_schema"], promotion=True)
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert "decision:receipt_must_not_promote_authority" in body["findings"]


def test_missing_receipt_fails_closed_without_crash(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    k.unlink()
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert "knowledge_graph:receipt_missing" in body["findings"]


def test_preflight_reports_missing_tools_and_env_without_printing_secret_values(monkeypatch):
    for name in (
        "DECISION_SOR_PLATFORM_URL",
        "DECISION_SOR_SERVICE_URL",
        "DECISION_SOR_ADMIN_DATABASE_URL",
        "DECISION_SOR_PLATFORM_ROLE",
        "DATABASE_URL",
        "SAHOOL_AGENT_TOKEN",
        "FIELD_SERVICE_URL",
        "TENANT_A",
        "TENANT_B",
        "FIELD_A",
        "KG_SERVICE_URL",
        "KG_TENANT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    body = mod.preflight(SHA)
    assert body["classification"] == "FAILED"
    assert "missing_tool:psql" in body["findings"]
    assert "missing_env:SAHOOL_AGENT_TOKEN" in body["findings"]
    rendered = json.dumps(body)
    assert "postgres://" not in rendered
    assert "Bearer " not in rendered


def test_preflight_binds_collection_checkout_to_exact_subject(monkeypatch):
    required = (
        "DECISION_SOR_PLATFORM_URL",
        "DECISION_SOR_SERVICE_URL",
        "DECISION_SOR_ADMIN_DATABASE_URL",
        "DECISION_SOR_PLATFORM_ROLE",
        "DATABASE_URL",
        "SAHOOL_AGENT_TOKEN",
        "FIELD_SERVICE_URL",
        "TENANT_A",
        "TENANT_B",
        "FIELD_A",
        "KG_SERVICE_URL",
        "KG_TENANT_ID",
    )
    for name in required:
        monkeypatch.setenv(name, "set")
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mod, "_run", lambda *a, **kw: {"returncode": 0, "output": "b" * 40})
    body = mod.preflight(SHA)
    assert body["classification"] == "FAILED"
    assert any(x.startswith("checkout_subject_sha_mismatch:") for x in body["findings"])


# ── PLATFORM-ROUTES-DUAL-S5-PRODUCER-01 — العطلُ الذي كذبه الحكمُ الأوّل ──────
#
# **العطلُ الحقيقيُّ ليس ما ظنّه أوّل قياس.** أوّلُ حكمٍ توهّم أنّ خطرَ الازدواج
# «مُنتِجٌ يحكم لنفسه فيمرّر إيصالاً كاذباً على الحارس» — وهذا سقط بالقياس:
# `verify_receipts` لا يقرأ حكمَ المُنتِج على نفسه، بل يُشغِّل الحارسَ القانونيّ
# ذاتَه على الملفّ (`_guard(...)`)، والحارسُ يُعيد اشتقاق حكمِه من `evidence`
# مستقلّاً — فمُنتِجٌ يكذب في تصنيفه الذاتيّ لا يجتاز حارساً يعيد القياس.
#
# **والعطلُ الحقيقيُّ مُثبَتٌ تجريبيّاً بمقارنةٍ مباشرة على خدمةٍ مرفوضة الاتّصال:**
# المُنتِجُ القديم (`decision_sor_live_closure_collector.py`) كان يلتقط أيَّ
# استثناء — بما فيها تعذّرُ الشبكة — **ويكتب إيصالاً على القرص** يدّعي
# `classification: FAILED`، فيُخرِج رمز `2`. أمّا القانونيّ
# (`s5_decision_live_closure_receipt.py`) فيُنهي برمز `1` **ولا يكتب شيئاً**.
# فتعذّرُ الوصول (مؤقّت، لا يعني شيئاً عن حالة القطع) كان يُسجَّل على القرص
# بصيغةِ «فشلٍ مُثبَت» دائم — وهو بعينه الخلطُ الذي حذّر منه توثيقُ المُنتِج
# القانونيّ نفسِه، مُثبَتاً هنا بتجربةٍ لا بادّعاء.


def test_the_orchestrator_calls_the_canonical_producer_not_the_duplicated_one():
    """المُنتِجُ القديم مُقصًى من السلك التشغيليّ، ولا يعود إليه بصمت.

    والمرساةُ **مسارٌ كاملٌ** لا مجرّدَ الاسم: الاسمُ المجرّد قد يبقى في تعليقٍ
    تاريخيٍّ يشرح سببَ التغيير — وذلك مقصودٌ لا انحراف. المرساةُ تمنع تحديداً
    عودةَ **سطر النداء** الذي كان يُشغِّل الملفَّ القديم.
    """
    src = PATH.read_text(encoding="utf-8")
    assert "scripts/architecture/s5_decision_live_closure_receipt.py" in src
    assert "scripts/staging/decision_sor_live_closure_collector.py" not in src, (
        "المُنتِج القديم عاد إلى سلك النداء الفعليّ — ممنوعٌ نهائياً (PLATFORM-ROUTES-DUAL-S5-PRODUCER-01)"
    )


def test_the_duplicated_producer_file_is_gone_not_merely_unwired():
    """إقصاءٌ فعليّ لا تعليقٌ مُهمَل — الملفُّ غائبٌ عن الشجرة."""
    assert not (ROOT / "scripts/staging/decision_sor_live_closure_collector.py").is_file()


def test_an_unreachable_decision_service_writes_no_receipt_via_the_wired_producer(
    tmp_path: Path,
):
    """الخاصّيّةُ التي كسرها المُنتِجُ القديم مُثبَتةٌ الآن عبر السلك الفعليّ.

    يُشغَّل السطرُ الحرفيُّ الذي يبنيه `collect()` — لا محاكاةً له — على مِنفَذٍ
    مرفوضِ الاتّصال، فيُقاس ما يقع فعلاً لا ما يُفترَض.
    """
    import subprocess
    import sys

    out = tmp_path / "decision.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/architecture/s5_decision_live_closure_receipt.py"),
            "--subject-sha",
            SHA,
            "--decision-url",
            "http://127.0.0.1:1",
            "--platform-url",
            "http://127.0.0.1:1",
            "--output",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 1, "عجزُ القياس يجب أن يُنهي برمز 1 — لا 0 ولا 2"
    assert not out.is_file(), "إيصالٌ كُتِب رغم تعذّر الاتّصال — تعذّرُ الوصول صار «فشلاً مُثبَتاً» على القرص"

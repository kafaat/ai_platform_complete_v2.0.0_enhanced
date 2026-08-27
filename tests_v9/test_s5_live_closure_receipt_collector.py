"""جامعُ إيصال S5 — الطرفُ المفقود من سلسلة C9.

**فجوةٌ لم تُسجَّل بمعرّفٍ بعد** — التسجيلُ محلُّه شريحةُ الدماغ لا شريحةُ
كود، وذكرُ معرّفٍ هنا كان سيكون **ادّعاءَ وجوده** (§٣.٧).

**العطل المقيس:** خمسةُ حرّاسٍ في `scripts/architecture/` يتحقّقون من إيصالات،
و**مُنتِجٌ واحد** يكتب إيصالاً. فحارسُ S5 جاهزٌ ومُكذَّبٌ بطفرةٍ مُسجَّلة،
و`c9_decision_authority_certification` يستدعيه، ولا شيء **يُنتِج** الإيصالَ الذي
ينتظره — فبقيت C9 عند `EVIDENCE_REQUIRED` **بنيويّاً** لا لغياب بيئة.

**والخاصّيّةُ الحاكمة ليست أنّ الجامع يعمل، بل أنّه لا يستطيع الكذب:** الحكمُ
يُشتقّ باستدعاء `findings_for` من الحارس نفسِه. فأيُّ شرطٍ يفرضه الحارسُ ولا
يستوفيه القياسُ يُسقِط `classification` حتماً — لا مجالَ لجامعٍ يُصنّف `PASSED`
على قياسٍ يرفضه المُتحقِّق.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "scripts" / "architecture"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


collector = _load("s5_collector", ARCH / "s5_decision_live_closure_receipt.py")
guard = _load("s5_guard", ARCH / "s5_decision_live_closure_receipt_guard.py")

SHA = "a" * 40
STAMP = "2026-08-26T20:00:00+00:00"


def _perms(write_denied: bool = True, select: bool = True) -> dict[str, Any]:
    return {
        "INSERT": not write_denied and True or False,
        "UPDATE": not write_denied and True or False,
        "DELETE": not write_denied and True or False,
        "SELECT": select,
    }


def _closed_evidence() -> dict[str, Any]:
    """قياسٌ مستوفٍ لكلّ شرطٍ يفرضه الحارس — الحالةُ الوحيدة التي تُنتِج PASSED."""
    role = "sahool_platform_app"
    return {
        "decision_runtime_identity": {
            "service": "decision-service",
            "git_sha": SHA,
            "metadata_source": "immutable-image-file",
        },
        "platform_runtime_identity": {
            "service": "sahool-platform",
            "git_sha": SHA,
            "metadata_source": "immutable-image-file",
        },
        "decision_ready": {
            "ready": True,
            "status": "ready",
            "sor_enabled": True,
            "mode": "system-of-record",
            "db_readiness": {"db_reachable": True, "migrations_current": True},
        },
        "decision_cutover_readiness": {
            "requested_sor": True,
            "can_enable_sor": True,
            "production_approved": True,
            "can_demote_platform": True,
            "missing_gates": [],
        },
        "platform_ready": {
            "decision_sor": {
                "requested_mode": "decision_service_sor",
                "effective_mode": "decision_service_sor",
                "platform_writes_required": False,
                "strict_decision_service_required": True,
                "demotion_allowed": True,
                "missing_gates": [],
            }
        },
        "role_certification": {
            "classification": "PASSED",
            "cutover_preflight_safe": True,
            "role_separation_confirmed": True,
            "blockers": [],
            "platform_role": role,
        },
        "platform_privilege_check": {
            "action": "check",
            "role": role,
            "after": {t: _perms() for t in guard.SOR_TABLES},
        },
    }


def test_a_fully_closed_measurement_yields_a_receipt_the_guard_accepts() -> None:
    """التكاملُ الحقيقيّ: ما يُنتِجه الجامعُ يجب أن يمرّ على المُتحقِّق."""
    receipt = collector.build_receipt(SHA, _closed_evidence(), guard, STAMP)
    assert receipt["classification"] == "PASSED"
    assert guard.findings_for(receipt, SHA) == []


def test_classification_agrees_with_the_guard_on_every_perturbation() -> None:
    """**الخاصّيّةُ الحاكمة:** `PASSED` ⟺ الحارسُ لا يجد ملاحظة.

    تُفحَص على تسعِ تشويهاتٍ لا على حالةٍ واحدة — فجامعٌ يصدق في الحالة السعيدة
    ويكذب في واحدةٍ من تسعٍ يبقى جامعاً يكذب.
    """
    perturbations: list[tuple[str, Any]] = [
        (
            "decision_runtime_identity",
            {"service": "wrong", "git_sha": SHA, "metadata_source": "immutable-image-file"},
        ),
        (
            "platform_runtime_identity",
            {
                "service": "sahool-platform",
                "git_sha": "b" * 40,
                "metadata_source": "immutable-image-file",
            },
        ),
        (
            "decision_ready",
            {
                "ready": False,
                "status": "ready",
                "sor_enabled": True,
                "mode": "system-of-record",
                "db_readiness": {"db_reachable": True, "migrations_current": True},
            },
        ),
        (
            "decision_cutover_readiness",
            {
                "requested_sor": True,
                "can_enable_sor": True,
                "production_approved": True,
                "can_demote_platform": True,
                "missing_gates": ["approval"],
            },
        ),
        (
            "platform_ready",
            {
                "decision_sor": {
                    "requested_mode": "decision_service_sor",
                    "effective_mode": "platform",
                    "platform_writes_required": False,
                    "strict_decision_service_required": True,
                    "demotion_allowed": True,
                    "missing_gates": [],
                }
            },
        ),
        (
            "role_certification",
            {
                "classification": "FAILED",
                "cutover_preflight_safe": True,
                "role_separation_confirmed": True,
                "blockers": [],
                "platform_role": "r",
            },
        ),
        (
            "role_certification",
            {
                "classification": "PASSED",
                "cutover_preflight_safe": True,
                "role_separation_confirmed": True,
                "blockers": ["x"],
                "platform_role": "r",
            },
        ),
        (
            "platform_privilege_check",
            {
                "action": "check",
                "role": "sahool_platform_app",
                "after": {t: _perms(write_denied=False) for t in guard.SOR_TABLES},
            },
        ),
        (
            "platform_privilege_check",
            {
                "action": "check",
                "role": "sahool_platform_app",
                "after": {t: _perms(select=False) for t in guard.SOR_TABLES},
            },
        ),
        (
            "platform_ready",
            {
                "decision_sor": {
                    "requested_mode": "decision_service_sor",
                    "effective_mode": "decision_service_sor",
                    "platform_writes_required": True,
                    "strict_decision_service_required": True,
                    "demotion_allowed": True,
                    "missing_gates": [],
                }
            },
        ),
    ]
    for key, bad in perturbations:
        ev = _closed_evidence()
        ev[key] = bad
        receipt = collector.build_receipt(SHA, ev, guard, STAMP)
        agrees = (receipt["classification"] == "PASSED") == (guard.findings_for(receipt, SHA) == [])
        assert agrees, f"الجامعُ خالف الحارسَ عند تشويه {key}"
        assert receipt["classification"] == "FAILED", f"تشويه {key} مرّ كـPASSED"


def test_the_historical_overclaim_is_structurally_impossible() -> None:
    """`historical_zero_platform_writes_measured` مثبَّتٌ `false` **بالبناء**.

    **والصياغةُ الأولى لهذا الاختبار نجت منها طفرةٌ حقيقيّة:** جعلتُ الحقلَ
    `bool(evidence.get("hz"))` فمرّ الاختبارُ أخضر — لأنّي كنتُ أُمرّر مُدخَلين
    لا يحملان ذلك المفتاح، فأُثبِت **القيمة** لا **الاستقلال**. اختبارٌ يمرّ
    ليس اختباراً يحرس.

    فالفحصُ الآن على شقّين: مسحُ مُدخَلاتٍ عدائيّة تحمل كلَّ مفتاحٍ محتمل،
    **وقيدٌ بنيويّ** على المصدر نفسِه — الحقلُ حرفيّةٌ لا تعبيرٌ يقرأ شيئاً.
    """
    hostile = {
        **_closed_evidence(),
        "hz": True,
        "historical": True,
        "historical_zero": True,
        "historical_zero_platform_writes_measured": True,
        "claims": {"historical_zero_platform_writes_measured": True},
    }
    for ev in (_closed_evidence(), {}, hostile):
        r = collector.build_receipt(SHA, ev, guard, STAMP)
        assert r["claims"]["historical_zero_platform_writes_measured"] is False

    # القيدُ البنيويّ: السطرُ حرفيّةٌ `False`، لا تعبيرٌ يقرأ مُدخَلاً.
    src = (ARCH / "s5_decision_live_closure_receipt.py").read_text(encoding="utf-8")
    line = next(
        ln
        for ln in src.splitlines()
        if '"historical_zero_platform_writes_measured"' in ln and ":" in ln.split("#")[0]
    )
    value = line.split(":", 1)[1].strip().rstrip(",")
    assert value == "False", f"الحقلُ صار تعبيراً يقرأ مُدخَلاً: {value}"


def test_the_write_enforcement_claim_is_measured_not_assumed() -> None:
    """ادّعاءُ منعِ الكتابة يُشتقّ من الامتيازات المقروءة — جدولٌ واحدٌ يكفي لنفيه."""
    ok = {t: _perms() for t in guard.SOR_TABLES}
    assert collector.write_enforcement_proven({"after": ok}, guard.SOR_TABLES) is True

    leaky = dict(ok)
    leaky[guard.SOR_TABLES[0]] = _perms(write_denied=False)
    assert collector.write_enforcement_proven({"after": leaky}, guard.SOR_TABLES) is False

    assert collector.write_enforcement_proven({}, guard.SOR_TABLES) is False


def test_the_receipt_is_read_only_and_never_promotes_authority() -> None:
    r = collector.build_receipt(SHA, _closed_evidence(), guard, STAMP)
    assert r["read_only"] is True
    assert r["authority_promotion"] is False
    assert r["schema"] == guard.SCHEMA


def test_binding_is_mandatory_and_a_bad_sha_writes_nothing(tmp_path: Path) -> None:
    """«لا إيصالَ بلا مَربِط» — وإلّا صار الدليلُ قابلاً لإعادة الاستعمال على شجرةٍ أخرى."""
    out = tmp_path / "r.json"
    rc = collector.main(
        [
            "--subject-sha",
            "not-a-sha",
            "--decision-url",
            "http://x",
            "--platform-url",
            "http://y",
            "--output",
            str(out),
        ]
    )
    assert rc == 1
    assert not out.exists()


def test_inability_to_measure_exits_one_and_writes_no_receipt(tmp_path: Path) -> None:
    """«تعذّر الوصول» ليس «فشلاً مُثبَتاً».

    خدمةٌ لا تستجيب ⇒ رمز 1 **ولا إيصال**. ولو كُتِب إيصالٌ بـ`FAILED` هنا لصار
    عطلُ الشبكة دليلاً على أنّ التحوّل غيرُ مُغلَق — وهو ادّعاءٌ لم يُقَس.
    """
    out = tmp_path / "r.json"
    rc = collector.main(
        [
            "--subject-sha",
            SHA,
            "--decision-url",
            "http://127.0.0.1:1",  # منفذٌ مغلقٌ يقيناً
            "--platform-url",
            "http://127.0.0.1:1",
            "--output",
            str(out),
        ]
    )
    assert rc == 1
    assert not out.exists()


def test_a_local_script_exiting_nonzero_is_not_read_as_a_measurement_failure() -> None:
    """`decision_sor_role_certify` يُنهي بـ2 عند `classification != PASSED`.

    وذلك **قياسٌ ناجح لحالةٍ سالبة**. فلو قرأ الجامعُ رمزَ الخروج عجزاً لأنهى
    بـ1 ولم يكتب إيصالاً — فتضيع الحالةُ السالبة التي كان يجب أن تُوثَّق.
    """
    src = (ARCH / "s5_decision_live_closure_receipt.py").read_text(encoding="utf-8")
    body = src.split("def run_json", 1)[1].split("\ndef ", 1)[0]
    assert "returncode" not in body.replace("proc.returncode}", ""), (
        "run_json يقرأ رمزَ الخروج حكماً — الحكمُ في الجسم لا في الرمز"
    )
    assert "proc.stdout" in body


def test_a_hanging_local_script_is_a_measurement_failure_not_an_indefinite_hang(
    tmp_path: Path, monkeypatch
) -> None:
    """سكربتٌ محلّيٌّ عالقٌ عجزٌ عن القياس — لا انتظارٌ بلا نهاية.

    بلا مهلةٍ محلّيّة صريحة، سكربتٌ حقيقيٌّ عالقٌ (اتّصال قاعدة بيانات مُعلَّق)
    كان سيُبقي هذا القياسَ مُعلَّقاً حتّى مهلة المنسِّق الخارجيّة الأكبر بكثير.

    **الخاصّيّةُ المحروسة هي السرعةُ لا مجرّدَ نوع الاستثناء:** `run_json` على
    سكربتٍ صامتٍ عالقٍ يرفع `MeasurementError` **بأيّ حال** — إمّا فوراً عبر
    المهلة، أو بعد اكتمال السكربت لأنّه لم يطبع شيئاً. فتأكيدٌ يفحص نوعَ
    الاستثناء وحده يمرّ حتى لو أُسقِطت المهلةُ تماماً؛ ولذا يُقاس الزمنُ المنقضي
    صريحاً: أقلُّ من مهلةِ الاختبار بكثير، لا مجرّد "رُفِع استثناءٌ ما أخيراً".
    """
    import time

    monkeypatch.setattr(collector, "_LOCAL_SCRIPT_TIMEOUT_SECONDS", 1)
    hanging = tmp_path / "hangs.py"
    hanging.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
    started = time.monotonic()
    with pytest.raises(collector.MeasurementError):
        collector.run_json(hanging)
    elapsed = time.monotonic() - started
    assert elapsed < 5, (
        f"استغرق {elapsed:.1f}ث — المهلةُ المحلّيّة لم تُطبَّق فعليّاً، والقياسُ انتظر اكتمال السكربت"
    )


def test_the_collector_does_not_reimplement_the_guard_rules() -> None:
    """مصدرُ الشروط واحد.

    جامعٌ يُعيد كتابة شروط الحارس ينحرف عنها بصمت — فيُنتِج إيصالاً يظنّه صالحاً
    وترفضه البوّابة. فالحكمُ يُستدعى من الحارس، ولا تُكرَّر مفرداتُه هنا.
    """
    src = (ARCH / "s5_decision_live_closure_receipt.py").read_text(encoding="utf-8")
    assert "guard.findings_for(" in src, "الحكمُ لا يُشتقّ من الحارس"
    for leaked in ("system-of-record", "immutable-image-file", "decision_service_sor"):
        assert leaked not in src, f"شرطُ الحارس {leaked!r} مُعاد كتابته في الجامع"


def test_the_emitted_receipt_round_trips_as_json() -> None:
    r = collector.build_receipt(SHA, _closed_evidence(), guard, STAMP)
    assert json.loads(json.dumps(r, ensure_ascii=False)) == r

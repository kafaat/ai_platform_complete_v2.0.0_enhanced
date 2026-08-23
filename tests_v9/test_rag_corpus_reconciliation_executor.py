"""منفّذ التسوية — البوّابة مغلقةٌ على HOLD ولا تكتب إلا بذراً قانونيّاً مستثنياً للمحجور.

الأحكام المثبَّتة هنا أحكامُ المالك لا اجتهاد الأداة: التفرّد المنطقيّ على كامل
المجموعة بما فيها الحجر · «أيّ HOLD_LOGICAL_ID_COLLISION يبقى HOLD ولا يُنفَّذ
ضدّه شيء» · لا حذف يدويّاً لنقاط Qdrant · والحكم النهائيّ لا يكون PASS إلا
باخضرار الثلاث عشرة خطوةً كلّها — «لم أنظر» ليس «لا يوجد».
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "scripts/architecture/rag_corpus_reconciliation_executor.py"
SEEDER = ROOT / "services/qdrant-seed/seed.py"


def _load():
    spec = importlib.util.spec_from_file_location("test_recon_executor", EXECUTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_recon_executor"] = module
    spec.loader.exec_module(module)
    return module


def _record(point_id: str, logical: str | None, tenant: str = "tenant-a") -> dict:
    return {
        "point_id": point_id,
        "tenant_id": tenant,
        "scope": "quarantine" if tenant == "__seed_quarantine__" else "tenant",
        "explicit_logical_chunk_id": logical,
    }


def _receipt(records: list[dict], *, declared_groups: int | None = None) -> dict:
    by_logical: dict[str, int] = {}
    for row in records:
        if row.get("explicit_logical_chunk_id"):
            key = str(row["explicit_logical_chunk_id"])
            by_logical[key] = by_logical.get(key, 0) + 1
    groups = [k for k, n in by_logical.items() if n >= 2]
    part: dict[str, int] = {}
    for row in records:
        part[row["scope"]] = part.get(row["scope"], 0) + 1
    return {
        "point_count": len(records),
        "physical_partition": part,
        "logical_identity": {
            "scope": "collection",
            "quarantine_included": True,
            "collision_group_count": len(groups) if declared_groups is None else declared_groups,
            "collision_point_count": sum(by_logical[k] for k in groups),
        },
        "point_records": records,
    }


def _plan_for(receipt: dict, *, collision_action: str = "HOLD_LOGICAL_ID_COLLISION") -> dict:
    by_logical: dict[str, int] = {}
    for row in receipt["point_records"]:
        if row.get("explicit_logical_chunk_id"):
            key = str(row["explicit_logical_chunk_id"])
            by_logical[key] = by_logical.get(key, 0) + 1
    rows = []
    for row in receipt["point_records"]:
        logical = row.get("explicit_logical_chunk_id")
        colliding = bool(logical and by_logical.get(str(logical), 0) >= 2)
        rows.append(
            {
                "point_id": row["point_id"],
                "explicit_logical_chunk_id": logical,
                "action": collision_action if colliding else "NOOP_CANONICAL",
            }
        )
    return {"migration_authorized": False, "writes_performed": False, "plan_rows": rows}


def _args(tmp_path: Path, *, execute: bool = False, identity_map: str | None = None):
    return argparse.Namespace(
        subject_sha="a" * 40,
        subject_tree="b" * 40,
        evidence_dir=str(tmp_path / "evidence"),
        qdrant_url="http://sahool-qdrant:6333",
        collection="sahool_agri_kb",
        identity_map=identity_map,
        deployment_artifact="ghcr.io/example/rag:test",
        deployment_artifact_digest="sha256:" + "c" * 64,
        seed_tenant="__global__",
        e2e_cmd="true",
        execute=execute,
        output=None,
    )


def _d09_green() -> dict:
    return {
        "checklist": {
            "identity_match": True,
            "no_live_mutation": True,
            "readyz": True,
            "observation": True,
        },
        "d09_e": {"problems": []},
    }


def _runners(pre: dict, post: dict | None = None, d09: dict | None = None, calls=None):
    calls = calls if calls is not None else []
    audits = iter([pre] + ([post] if post is not None else []))

    def audit(output):
        receipt = next(audits)
        output.write_text(json.dumps(receipt), encoding="utf-8")
        calls.append(("audit", str(output.name)))
        return receipt

    def plan(receipt_path, output):
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
        built = _plan_for(receipt)
        output.write_text(json.dumps(built), encoding="utf-8")
        calls.append(("plan", str(output.name)))
        return built

    def d09_runner(output):
        receipt = d09 if d09 is not None else _d09_green()
        output.write_text(json.dumps(receipt), encoding="utf-8")
        calls.append(("d09", str(output.name)))
        return receipt

    def seed(exclusions_path):
        calls.append(("seed", json.loads(Path(exclusions_path).read_text(encoding="utf-8"))))

    def e2e():
        calls.append(("e2e", None))

    return {"audit": audit, "plan": plan, "d09": d09_runner, "seed": seed, "e2e": e2e}, calls


def test_a_receipt_without_the_extension_is_refused_before_anything_runs(tmp_path) -> None:
    ex = _load()
    bare = {"exact_count": 3, "point_records": []}
    assert ex.require_extended_receipt(bare)
    runners, calls = _runners(bare)
    receipt = ex.run(_args(tmp_path, execute=True), runners)
    assert receipt["steps"]["d08_pre"]["status"] == "FAIL"
    assert receipt["verdict"] == "FAIL"
    assert receipt["writes_performed"] is False
    assert not [c for c in calls if c[0] == "seed"], "لا كتابة على قياسٍ مرفوض"


def test_collision_identities_derive_from_records_and_tamper_is_named(tmp_path) -> None:
    ex = _load()
    records = []
    for g in range(7):  # فوق سقف العيّنات (٥) عمداً
        records.append(_record(f"p{g}a", f"dup-{g}"))
        records.append(_record(f"p{g}b", f"dup-{g}", tenant="__seed_quarantine__"))
    receipt = _receipt(records)
    assert len(ex.collision_logical_ids(receipt)) == 7
    with pytest.raises(ValueError, match="disagrees"):
        ex.collision_logical_ids(_receipt(records, declared_groups=3))


def test_the_identity_map_gate_holds_without_the_owner_and_grants_no_authority() -> None:
    ex = _load()
    ids = ["dup-1"]
    assert ex.identity_map_gate(ids, None)[0] == "HOLD"
    assert ex.identity_map_gate(ids, {"collisions": {}})[0] == "HOLD"
    migrate = {"collisions": {"dup-1": {"disposition": "migrate"}}}
    status, problems = ex.identity_map_gate(ids, migrate)
    assert status == "HOLD" and any("only authorized to keep holds held" in p for p in problems)
    assert (
        ex.identity_map_gate(ids, {"collisions": {"dup-1": {"disposition": "hold"}}})[0] == "PASS"
    )
    assert ex.identity_map_gate([], None)[0] == "PASS"


def test_a_collision_member_slated_for_any_action_fails_the_hold_gate() -> None:
    ex = _load()
    receipt = _receipt([_record("p1", "dup-1"), _record("p2", "dup-1")])
    plan = _plan_for(receipt, collision_action="MIGRATION_CANDIDATE")
    status, problems = ex.collision_hold_gate(["dup-1"], plan)
    assert status == "FAIL" and any("no action but hold" in p for p in problems)
    # فعلٌ مجهول ليس «آمناً افتراضيّاً» — التصنيف مقفول.
    status, _ = ex.collision_hold_gate(["dup-1"], _plan_for(receipt, collision_action="REWRITE"))
    assert status == "FAIL"
    assert ex.collision_hold_gate(["dup-1"], _plan_for(receipt))[0] == "PASS"


def test_dry_run_measures_reports_and_never_passes(tmp_path) -> None:
    ex = _load()
    clean = _receipt([_record("p1", "c1"), _record("p2", "c2")])
    runners, calls = _runners(clean)
    receipt = ex.run(_args(tmp_path, execute=False), runners)
    assert receipt["steps"]["d08_pre"]["status"] == "PASS"
    assert receipt["steps"]["canonical_seeding"]["status"] == "NOT_MEASURED"
    assert receipt["verdict"] == "INCOMPLETE", "«لم أنظر» ليس «لا يوجد» — ولا PASS بلا الثلاث عشرة"
    assert receipt["writes_performed"] is False
    assert not [c for c in calls if c[0] == "seed"]


def test_full_execute_on_a_clean_corpus_passes_all_thirteen(tmp_path) -> None:
    ex = _load()
    clean = _receipt([_record("p1", "c1"), _record("p2", "c2")])
    runners, calls = _runners(clean, post=clean)
    receipt = ex.run(_args(tmp_path, execute=True), runners)
    assert receipt["verdict"] == "PASS"
    assert [s["status"] for s in receipt["steps"].values()].count("PASS") == 13
    assert receipt["writes_performed"] is True
    assert receipt["deletion_performed"] is False, "لا حذف يدويّاً لنقاط Qdrant — أبداً"
    (seed_call,) = [c for c in calls if c[0] == "seed"]
    assert seed_call[1]["exclude_chunk_ids"] == []


def test_held_identities_are_excluded_from_seeding_and_residue_yields_hold(tmp_path) -> None:
    ex = _load()
    records = [
        _record("p1", "dup-1"),
        _record("p2", "dup-1", tenant="__seed_quarantine__"),
        _record("p3", "c3"),
    ]
    dirty = _receipt(records)
    identity_map = tmp_path / "identity-map.json"
    identity_map.write_text(
        json.dumps({"collisions": {"dup-1": {"disposition": "hold"}}}), encoding="utf-8"
    )
    runners, calls = _runners(dirty, post=dirty)
    receipt = ex.run(_args(tmp_path, execute=True, identity_map=str(identity_map)), runners)
    (seed_call,) = [c for c in calls if c[0] == "seed"]
    assert seed_call[1]["exclude_chunk_ids"] == ["dup-1"], (
        "«لا يُنفَّذ ضدّ HOLD شيء» — الهويّة المحجورة خارج البذر لا داخله"
    )
    assert receipt["steps"]["global_duplicates_zero"]["status"] == "HOLD"
    assert receipt["verdict"] == "HOLD", "بقايا التصادم حكمها HOLD يعود للمالك — لا «نجاح جزئيّ»"


def test_d09_checklist_absence_is_never_read_as_a_pass() -> None:
    ex = _load()
    steps = ex.d09_checklist_steps({"checklist": {"identity_match": True}})
    assert steps["m1_m2_agreement"][0] == "FAIL"
    assert steps["readyz"][0] == "FAIL"
    steps = ex.d09_checklist_steps({})
    assert all(status == "FAIL" for status, _ in steps.values())


def test_the_seeder_reads_the_exclusion_file_fail_closed() -> None:
    """البذّار يعتمد على qdrant_client غير المتاح هنا — فالعقد يُثبَت على مصدره نصّاً."""
    text = SEEDER.read_text(encoding="utf-8")
    assert "QDRANT_SEED_EXCLUDE_CHUNK_IDS_FILE" in text
    assert "_load_excluded_chunk_ids" in text
    assert "f\"seed:{doc['id']}\" not in excluded" in text
    filter_at = text.index("knowledge = [doc for doc in KNOWLEDGE_BASE")
    embed_at = text.index("for doc in knowledge]")
    assert filter_at < embed_at, "الاستثناء قبل التضمين — لا وثيقة تُضمَّن ثم تُسقَط"
    assert text.count("for doc in KNOWLEDGE_BASE]") == 0, (
        "حلقة البذر يجب أن تقرأ القائمة المُستثناة لا الأصل"
    )


def test_the_live_d09_runner_carries_the_full_binding() -> None:
    """أداة D09 تُلزم بالمصنوعة وبصمتها معاً — منفّذٌ يمرّر نصف الربط يفشل مغلقاً دائماً.

    المنفّذون الحيّون subprocess فلا يغطّيهم زرع الوحدات؛ العقد يُثبَت على المصدر
    نصّاً أسوة باختبارات البذّار: العلمان حاضران في استدعاء d09 الحيّ.
    """
    text = EXECUTOR.read_text(encoding="utf-8")
    assert '"--deployment-artifact-digest",' in text
    assert "args.deployment_artifact_digest," in text

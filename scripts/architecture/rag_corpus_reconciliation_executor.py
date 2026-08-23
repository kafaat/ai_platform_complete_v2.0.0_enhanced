#!/usr/bin/env python3
"""منفّذ تسوية جسم RAG — بوّابة القبول ذات الثلاث عشرة خطوة، مغلقةً على HOLD.

``CORPUS-RECONCILIATION-01``. كُتب بتفويضٍ صريحٍ من المالك بعد أن سُمّي بالاسم،
وبعد حكمين لا يجتهد هذا المنفّذ فوقهما:

* **التفرّد المنطقيّ على كامل المجموعة** بما فيها ``__seed_quarantine__`` —
  يقرؤه من ``logical_identity`` في إيصال D08 الممتدّ ولا يعيد اشتقاقه.
* **«أيّ ``HOLD_LOGICAL_ID_COLLISION`` يبقى HOLD ولا يُنفَّذ ضدّه شيء»** —
  فالمسار الكتابيّ الوحيد هنا هو **البذر القانونيّ** (upsert على مُعرِّفات
  ``canonical_storage_point_id`` الحتميّة؛ لا حذف يدويّاً لنقاط Qdrant أبداً)،
  وكلّ هويّةٍ منطقيّةٍ عالقةٍ في مجموعة تصادمٍ تُستثنى من البذر صراحةً عبر
  ملفّ استثناءٍ يقرؤه البذّار — فلا كتابة، ولو بالتقارب، فوق عضو مجموعةٍ محجورة.

**الوضع الافتراضيّ قراءةٌ وتقرير.** بلا ``--execute`` تُنفَّذ الخطوات ١–٥
(قياسات قراءةٍ فقط) ويُكتب إيصالٌ حكمُه ``INCOMPLETE`` أبداً لا ``PASS`` —
«لم أنظر» ليس «لا يوجد». ومع ``--execute`` تُضاف ٦–١٣، ولا يكون الحكم ``PASS``
إلا إذا خضِرت الثلاث عشرة كلّها؛ أيّ تصادمٍ باقٍ بعد البذر يجعل الحكم ``HOLD``
مع تقريرٍ يسمّي المجموعات — القرار فيها للمالك لا لهذه الأداة.

الخطوات (بترتيب المالك):
١ ``d08_pre`` · ٢ ``identity_map`` · ٣ ``d12_plan`` · ٤ ``collisions_proven_or_hold``
· ٥ ``d09_pre_receipt`` · ٦ ``canonical_seeding`` · ٧ ``d08_post`` ·
٨ ``global_duplicates_zero`` · ٩ ``m1_m2_agreement`` · ١٠ ``d09e_pass`` ·
١١ ``readyz`` · ١٢ ``search`` · ١٣ ``e2e``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = "sahool.rag-corpus-reconciliation-receipt/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")

STEPS = (
    "d08_pre",
    "identity_map",
    "d12_plan",
    "collisions_proven_or_hold",
    "d09_pre_receipt",
    "canonical_seeding",
    "d08_post",
    "global_duplicates_zero",
    "m1_m2_agreement",
    "d09e_pass",
    "readyz",
    "search",
    "e2e",
)

# أفعال HOLD المعروفة لمخطّط D12 — التصنيف مقفول: فعلٌ غير معروفٍ ليس «آمناً
# افتراضيّاً» بل سببُ رفضٍ، كي لا يُقرأ فعلٌ جديد لم يُدقَّق على أنّه حجر.
_HOLD_ACTIONS = frozenset(
    {
        "HOLD_LOGICAL_ID_COLLISION",
        "HOLD_IDENTITY_EVIDENCE",
        "HOLD_PROVENANCE_EVIDENCE",
        "HOLD_UNATTRIBUTED",
        "HOLD_INVALID",
    }
)
_SAFE_NONWRITE_ACTIONS = frozenset({"NOOP_CANONICAL"}) | _HOLD_ACTIONS


def _sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def require_extended_receipt(receipt: dict[str, Any]) -> list[str]:
    """فشلٌ مغلق إن غاب امتداد D08 — البوّابة لا تعمل على إيصالٍ أعمى عن التفرّد."""
    problems: list[str] = []
    pc = receipt.get("point_count")
    if not isinstance(pc, int) or pc < 0:
        problems.append("point_count missing: the receipt predates D08-EXT — refuse, do not infer")
    part = receipt.get("physical_partition")
    if not isinstance(part, dict) or not part:
        problems.append("physical_partition missing")
    else:
        if not all(isinstance(v, int) and v >= 0 for v in part.values()):
            problems.append("physical_partition values must be non-negative integers")
        elif isinstance(pc, int) and sum(part.values()) != pc:
            problems.append(f"physical_partition sum {sum(part.values())} != point_count {pc}")
        banned = [
            k
            for k in part
            if any(w in str(k).lower() for w in ("collision", "duplicate", "logical"))
        ]
        if banned:
            problems.append(f"physical_partition carries a collision axis: {sorted(banned)}")
    li = receipt.get("logical_identity")
    if not isinstance(li, dict):
        problems.append("logical_identity missing")
        return problems
    if li.get("scope") != "collection":
        problems.append(f"logical_identity.scope must be 'collection' (got {li.get('scope')!r})")
    if li.get("quarantine_included") is not True:
        problems.append("logical_identity.quarantine_included must be true")
    g = li.get("collision_group_count")
    p = li.get("collision_point_count")
    if not isinstance(g, int) or not isinstance(p, int) or g < 0 or p < 0:
        problems.append("collision counts missing or invalid")
    elif g > 0 and p < 2 * g:
        problems.append(f"collision_point_count {p} < 2*collision_group_count {g}")
    return problems


def collision_logical_ids(receipt: dict[str, Any]) -> list[str]:
    """الهويّات المنطقيّة المتصادمة — تُشتقّ من سجلّات الإيصال نفسها لا من العيّنات.

    العيّنات محدودةٌ عمداً (≤٥ مجموعات) فلا تصلح ميدانَ استثناء: استثناءٌ مبنيّ
    عليها يترك مجموعاتٍ بلا حماية حين تتجاوز التصادماتُ سقفَ العيّنات.
    """
    records = receipt.get("point_records")
    if not isinstance(records, list):
        raise ValueError("point_records missing — cannot derive collision identities")
    by_logical: dict[str, int] = {}
    for row in records:
        logical = row.get("explicit_logical_chunk_id") if isinstance(row, dict) else None
        if logical:
            by_logical[str(logical)] = by_logical.get(str(logical), 0) + 1
    derived = sorted(k for k, n in by_logical.items() if n >= 2)
    li = receipt.get("logical_identity") or {}
    declared = li.get("collision_group_count")
    if isinstance(declared, int) and declared != len(derived):
        raise ValueError(
            f"collision_group_count {declared} disagrees with point_records ({len(derived)}) — "
            "tampered or truncated receipt"
        )
    return derived


def identity_map_gate(
    collision_ids: list[str], identity_map: dict[str, Any] | None
) -> tuple[str, list[str]]:
    """الخطوة ٢: خريطة الهويّة تُثبت أنّ المالك رأى كلّ تصادم، ولا تمنح سلطةً فوق HOLD."""
    if not collision_ids:
        return "PASS", []
    if identity_map is None:
        return "HOLD", [
            "collisions exist and no identity map was provided — owner inventory required"
        ]
    entries = identity_map.get("collisions")
    if not isinstance(entries, dict):
        return "HOLD", ["identity map lacks a 'collisions' object"]
    problems: list[str] = []
    for logical in collision_ids:
        entry = entries.get(logical)
        if not isinstance(entry, dict):
            problems.append(f"collision {logical!r} absent from the identity map")
            continue
        if entry.get("disposition") != "hold":
            # الحكم القائم: HOLD يبقى HOLD. أيّ تصرّفٍ آخر في الخريطة يتجاوز
            # تفويضَ هذه الأداة فيُرفَض هنا لا يُنفَّذ خطأً.
            problems.append(
                f"collision {logical!r} carries disposition {entry.get('disposition')!r}; "
                "this executor is only authorized to keep holds held"
            )
    return ("HOLD" if problems else "PASS"), problems


def collision_hold_gate(collision_ids: list[str], plan: dict[str, Any]) -> tuple[str, list[str]]:
    """الخطوة ٤: مثبَتٌ أو محجور — كلّ عضو مجموعةِ تصادمٍ فعلُه في الخطّة حجرٌ صريح."""
    if not collision_ids:
        return "PASS", []
    rows = plan.get("plan_rows")
    if not isinstance(rows, list):
        return "FAIL", ["plan_rows missing from the D12 plan"]
    colliding = set(collision_ids)
    problems: list[str] = []
    seen_logicals: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        logical = row.get("explicit_logical_chunk_id")
        if logical is None or str(logical) not in colliding:
            continue
        seen_logicals.add(str(logical))
        action = str(row.get("action"))
        if action not in _SAFE_NONWRITE_ACTIONS:
            problems.append(
                f"collision member {row.get('point_id')!r} ({logical!r}) is slated for "
                f"{action!r} — a collision group accepts no action but hold"
            )
    unseen = sorted(colliding - seen_logicals)
    if unseen:
        problems.append(f"collision identities absent from the plan: {unseen}")
    return ("FAIL" if problems else "PASS"), problems


def seeding_exclusions(collision_ids: list[str]) -> dict[str, Any]:
    """ملفّ الاستثناء الذي يقرؤه البذّار: لا كتابة — ولو تقارباً — فوق هويّةٍ محجورة."""
    return {
        "schema": "sahool.rag-seed-exclusions/v1",
        "reason": "HOLD_LOGICAL_ID_COLLISION stays held; canonical seeding must not touch it",
        "exclude_chunk_ids": sorted(collision_ids),
    }


def post_uniqueness_gate(receipt_post: dict[str, Any]) -> tuple[str, list[str]]:
    """الخطوة ٨: صفرُ تكرارٍ منطقيّ عالميّاً — وإلا فالحكم HOLD لا «نجاحٌ جزئيّ»."""
    problems = require_extended_receipt(receipt_post)
    if problems:
        return "FAIL", problems
    li = receipt_post["logical_identity"]
    if li["collision_group_count"] != 0:
        return "HOLD", [
            f"{li['collision_group_count']} collision group(s) remain after canonical seeding — "
            "no deletion is authorized; adjudication returns to the owner"
        ]
    return "PASS", []


def d09_checklist_steps(d09_receipt: dict[str, Any]) -> dict[str, tuple[str, list[str]]]:
    """الخطوات ٩–١٢ تُقرأ من إيصال D09 الحيّ — قارئٌ مغلقٌ على الغياب لا مُخمِّن."""
    checklist = d09_receipt.get("checklist")
    if not isinstance(checklist, dict):
        missing: tuple[str, list[str]] = ("FAIL", ["d09 receipt carries no checklist"])
        return {name: missing for name in ("m1_m2_agreement", "d09e_pass", "readyz", "search")}

    def _bool_step(key: str, extra: str = "") -> tuple[str, list[str]]:
        value = checklist.get(key)
        if value is True:
            return "PASS", []
        if value is False:
            return "FAIL", [f"d09 checklist {key} is false{extra}"]
        return "FAIL", [f"d09 checklist {key} missing — absence is not a pass"]

    identity = _bool_step("identity_match")
    mutation = _bool_step("no_live_mutation")
    m1m2 = (
        ("PASS", [])
        if identity[0] == "PASS" and mutation[0] == "PASS"
        else ("FAIL", identity[1] + mutation[1])
    )
    d09e = d09_receipt.get("d09_e") or {}
    problems = d09e.get("problems") if isinstance(d09e, dict) else None
    if problems == []:
        d09e_step: tuple[str, list[str]] = ("PASS", [])
    elif isinstance(problems, list):
        d09e_step = ("FAIL", [str(p) for p in problems])
    else:
        d09e_step = ("FAIL", ["d09-e problems list missing — absence is not a pass"])
    return {
        "m1_m2_agreement": m1m2,
        "d09e_pass": d09e_step,
        "readyz": _bool_step("readyz"),
        "search": _bool_step("observation"),
    }


def final_verdict(steps: dict[str, dict[str, Any]]) -> str:
    statuses = [str(steps.get(name, {}).get("status", "NOT_MEASURED")) for name in STEPS]
    if any(s == "FAIL" for s in statuses):
        return "FAIL"
    if any(s == "HOLD" for s in statuses):
        return "HOLD"
    if all(s == "PASS" for s in statuses):
        return "PASS"
    return "INCOMPLETE"


def _validate_subject(value: str, label: str) -> str:
    value = value.lower()
    if not _HEX40.fullmatch(value):
        raise ValueError(f"{label} must be a full 40-character hex id")
    return value


def _default_runners(args: argparse.Namespace) -> dict[str, Callable[..., Any]]:
    """المنفّذون الحيّون — كلّ واحدٍ أمرٌ موجودٌ في الشجرة، لا منطقَ قرارٍ فيهم."""

    def _run(cmd: list[str]) -> None:
        proc = subprocess.run(cmd, cwd=ROOT, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")

    def audit(output: pathlib.Path) -> dict[str, Any]:
        _run(
            [
                sys.executable,
                "scripts/architecture/rag_live_corpus_audit.py",
                "--subject-sha",
                args.subject_sha,
                "--subject-tree",
                args.subject_tree,
                "--qdrant-url",
                args.qdrant_url,
                "--collection",
                args.collection,
                "--output",
                str(output),
            ]
        )
        return json.loads(output.read_text(encoding="utf-8"))

    def plan(receipt_path: pathlib.Path, output: pathlib.Path) -> dict[str, Any]:
        _run(
            [
                sys.executable,
                "scripts/architecture/rag_logical_identity_migration_plan.py",
                "--corpus-receipt",
                str(receipt_path),
                "--output",
                str(output),
            ]
        )
        _run(
            [
                sys.executable,
                "scripts/architecture/rag_logical_identity_migration_plan_guard.py",
                "--plan",
                str(output),
                "--corpus-receipt",
                str(receipt_path),
                "--subject-sha",
                args.subject_sha,
                "--subject-tree",
                args.subject_tree,
            ]
        )
        return json.loads(output.read_text(encoding="utf-8"))

    def d09(output: pathlib.Path) -> dict[str, Any]:
        _run(
            [
                sys.executable,
                "scripts/architecture/d09_live_evidence_receipt.py",
                "--subject-sha",
                args.subject_sha,
                "--subject-tree",
                args.subject_tree,
                "--deployment-artifact",
                args.deployment_artifact,
                "--output",
                str(output),
            ]
        )
        return json.loads(output.read_text(encoding="utf-8"))

    def seed(exclusions_path: pathlib.Path) -> None:
        env = dict(os.environ)
        env["QDRANT_SEED_TENANT_ID"] = args.seed_tenant
        env["QDRANT_SEED_EXCLUDE_CHUNK_IDS_FILE"] = str(exclusions_path)
        proc = subprocess.run(
            [sys.executable, "services/qdrant-seed/seed.py"], cwd=ROOT, env=env, check=False
        )
        if proc.returncode != 0:
            raise RuntimeError(f"canonical seeding failed ({proc.returncode})")

    def e2e() -> None:
        if not args.e2e_cmd:
            raise RuntimeError("no --e2e-cmd configured")
        proc = subprocess.run(args.e2e_cmd, shell=True, cwd=ROOT, check=False)  # noqa: S602
        if proc.returncode != 0:
            raise RuntimeError(f"e2e failed ({proc.returncode})")

    return {"audit": audit, "plan": plan, "d09": d09, "seed": seed, "e2e": e2e}


def run(
    args: argparse.Namespace, runners: dict[str, Callable[..., Any]] | None = None
) -> dict[str, Any]:
    runners = runners or _default_runners(args)
    evidence = pathlib.Path(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    steps: dict[str, dict[str, Any]] = {name: {"status": "NOT_MEASURED"} for name in STEPS}
    writes_performed = False
    identity_map = None
    if args.identity_map:
        identity_map = json.loads(pathlib.Path(args.identity_map).read_text(encoding="utf-8"))

    def _record(name: str, status: str, **extra: Any) -> None:
        steps[name] = {"status": status, **extra}

    stop = False
    pre_receipt: dict[str, Any] | None = None
    collision_ids: list[str] = []

    # ── ١) D08-pre ─────────────────────────────────────────────────────────
    pre_path = evidence / "corpus-audit-pre.json"
    try:
        pre_receipt = runners["audit"](pre_path)
        problems = require_extended_receipt(pre_receipt)
        if problems:
            _record("d08_pre", "FAIL", problems=problems)
            stop = True
        else:
            collision_ids = collision_logical_ids(pre_receipt)
            _record(
                "d08_pre",
                "PASS",
                receipt_sha256=_sha256_json(pre_receipt),
                collision_group_count=len(collision_ids),
            )
    except Exception as exc:  # noqa: BLE001 — كلّ فشل قياسٍ يُدوَّن ويوقف، لا يُبتلَع
        _record("d08_pre", "FAIL", problems=[str(exc)])
        stop = True

    # ── ٢) خريطة الهويّة ───────────────────────────────────────────────────
    if not stop:
        status, problems = identity_map_gate(collision_ids, identity_map)
        _record("identity_map", status, problems=problems)
        stop = status != "PASS"

    # ── ٣) D12 ────────────────────────────────────────────────────────────
    d12_plan: dict[str, Any] | None = None
    if not stop:
        try:
            d12_plan = runners["plan"](pre_path, evidence / "migration-plan.json")
            if d12_plan.get("migration_authorized") is not False or (
                d12_plan.get("writes_performed") is not False
            ):
                _record("d12_plan", "FAIL", problems=["unsafe D12 plan flags"])
                stop = True
            else:
                _record("d12_plan", "PASS", plan_sha256=_sha256_json(d12_plan))
        except Exception as exc:  # noqa: BLE001
            _record("d12_plan", "FAIL", problems=[str(exc)])
            stop = True

    # ── ٤) مثبَتٌ أو محجور ─────────────────────────────────────────────────
    if not stop and d12_plan is not None:
        status, problems = collision_hold_gate(collision_ids, d12_plan)
        _record("collisions_proven_or_hold", status, problems=problems)
        stop = status != "PASS"

    # ── ٥) إيصال D09 القَبْليّ ─────────────────────────────────────────────
    if not stop:
        try:
            d09_pre = runners["d09"](evidence / "d09-pre.json")
            _record("d09_pre_receipt", "PASS", receipt_sha256=_sha256_json(d09_pre))
        except Exception as exc:  # noqa: BLE001
            _record("d09_pre_receipt", "FAIL", problems=[str(exc)])
            stop = True

    # ── ٦–١٣) الكتابة وما بعدها — بتفويض ``--execute`` وحده ────────────────
    if not stop and args.execute:
        exclusions_path = evidence / "seed-exclusions.json"
        exclusions_path.write_text(
            json.dumps(seeding_exclusions(collision_ids), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            runners["seed"](exclusions_path)
            writes_performed = True
            _record(
                "canonical_seeding",
                "PASS",
                excluded_held_identities=len(collision_ids),
                exclusions_sha256=_sha256_json(seeding_exclusions(collision_ids)),
            )
        except Exception as exc:  # noqa: BLE001
            _record("canonical_seeding", "FAIL", problems=[str(exc)])
            stop = True

        if not stop:
            post_path = evidence / "corpus-audit-post.json"
            try:
                post_receipt = runners["audit"](post_path)
                problems = require_extended_receipt(post_receipt)
                if problems:
                    _record("d08_post", "FAIL", problems=problems)
                    stop = True
                else:
                    _record("d08_post", "PASS", receipt_sha256=_sha256_json(post_receipt))
                    status, problems = post_uniqueness_gate(post_receipt)
                    _record("global_duplicates_zero", status, problems=problems)
                    if status == "FAIL":
                        stop = True
            except Exception as exc:  # noqa: BLE001
                _record("d08_post", "FAIL", problems=[str(exc)])
                stop = True

        if not stop:
            try:
                d09_post = runners["d09"](evidence / "d09-post.json")
                for name, (status, problems) in d09_checklist_steps(d09_post).items():
                    _record(name, status, problems=problems)
            except Exception as exc:  # noqa: BLE001
                for name in ("m1_m2_agreement", "d09e_pass", "readyz", "search"):
                    _record(name, "FAIL", problems=[str(exc)])
                stop = True

        if not stop:
            try:
                runners["e2e"]()
                _record("e2e", "PASS")
            except Exception as exc:  # noqa: BLE001
                _record("e2e", "FAIL", problems=[str(exc)])

    receipt = {
        "schema": SCHEMA,
        "observed_at": datetime.now(UTC).isoformat(),
        "subject_sha": args.subject_sha,
        "subject_tree": args.subject_tree,
        "collection": args.collection,
        "execute_requested": bool(args.execute),
        "writes_performed": writes_performed,
        "deletion_performed": False,
        "held_collision_identities": collision_ids,
        "steps": steps,
        "verdict": final_verdict(steps),
    }
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject-sha", required=True)
    ap.add_argument("--subject-tree", required=True)
    ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://sahool-qdrant:6333"))
    ap.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "sahool_agri_kb"))
    ap.add_argument("--identity-map")
    ap.add_argument("--deployment-artifact", default="")
    ap.add_argument("--seed-tenant", default="__global__")
    ap.add_argument("--e2e-cmd", default="")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="يفعّل الخطوات الكتابيّة ٦–١٣؛ بدونه قياسٌ وتقرير لا غير",
    )
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    try:
        args.subject_sha = _validate_subject(args.subject_sha, "subject_sha")
        args.subject_tree = _validate_subject(args.subject_tree, "subject_tree")
        receipt = run(args)
    except Exception as exc:  # noqa: BLE001 — أداة دليلٍ تفشل مغلقةً بسطرٍ مقروء
        print(f"rag_corpus_reconciliation_fail {exc}", file=sys.stderr)
        return 1
    text = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        pathlib.Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    # الإيصال الصادق عن جسمٍ غير متسوٍّ دليلٌ لا فشلُ أداة — لكنّ FAIL يفشل الأمر.
    return 0 if receipt["verdict"] in {"PASS", "HOLD", "INCOMPLETE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

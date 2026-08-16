"""Behavioral contract for the conservative capability linker."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "capability_linker.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("capability_linker_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _minimal_repo(tmp_path: Path) -> tuple[Path, Path]:
    registry = tmp_path / "capabilities/registry/capabilities.json"
    generated = tmp_path / "capabilities/generated"
    registry.parent.mkdir(parents=True)
    generated.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "FM-001",
                        "maturity": 3,
                        "status": "runtime_instrumented_production_unverified",
                        "evidence_level": 4,
                        "services": [],
                        "apis": [],
                        "tests": [],
                        "ui_consumers": [],
                        "mobile_consumers": [],
                        "dependencies": [],
                        "evidence": [],
                        "owner": "PLATFORM",
                        "confidence": "low",
                        "rationale": "seed",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    service_main = tmp_path / "services/auth/main.py"
    service_main.parent.mkdir(parents=True)
    service_main.write_text("# tenant auth\n", encoding="utf-8")
    test_file = tmp_path / "tests/test_tenant_auth.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_tenant_auth(): pass\n", encoding="utf-8")
    _write_csv(
        tmp_path / "service_inventory.csv",
        ["service", "main"],
        [{"service": "auth", "main": "services/auth/main.py"}],
    )
    _write_csv(
        tmp_path / "route_inventory.csv",
        ["service", "method", "path", "file", "line", "function"],
        [
            {
                "service": "auth",
                "method": "GET",
                "path": "/tenant/auth",
                "file": "services/auth/main.py",
                "line": "1",
                "function": "tenant_auth",
            }
        ],
    )
    return registry, generated


def _configure(module, tmp_path: Path, registry: Path, generated: Path) -> None:
    module.ROOT = tmp_path
    module.REGISTRY = registry
    module.ROUTES = tmp_path / "route_inventory.csv"
    module.SERVICES = tmp_path / "service_inventory.csv"
    module.GENERATED = generated


def test_apply_links_shape_without_changing_certification(monkeypatch, tmp_path):
    module = _load_module()
    registry, generated = _minimal_repo(tmp_path)
    _configure(module, tmp_path, registry, generated)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply"])

    assert module.main() == 0
    capability = json.loads(registry.read_text(encoding="utf-8"))["capabilities"][0]
    assert capability["services"] == ["services/auth/main.py"]
    assert capability["apis"]
    assert capability["tests"] == ["tests/test_tenant_auth.py"]
    assert capability["status"] == "runtime_instrumented_production_unverified"
    assert capability["evidence_level"] == 4
    assert (generated / "capability_link_candidates.csv").is_file()


def test_check_is_pure_and_detects_both_registry_and_candidate_drift(monkeypatch, tmp_path):
    module = _load_module()
    registry, generated = _minimal_repo(tmp_path)
    _configure(module, tmp_path, registry, generated)

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply"])
    assert module.main() == 0
    candidates = generated / "capability_link_candidates.csv"
    before_registry = registry.read_bytes()
    before_candidates = candidates.read_bytes()

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check"])
    assert module.main() == 0
    assert registry.read_bytes() == before_registry
    assert candidates.read_bytes() == before_candidates

    candidates.write_text("drift\n", encoding="utf-8")
    drifted = candidates.read_bytes()
    assert module.main() == 1
    assert registry.read_bytes() == before_registry
    assert candidates.read_bytes() == drifted


def test_discover_files_excludes_claude_worktree_directories(monkeypatch, tmp_path):
    """CAPABILITY-LINKER-SCANS-AGENT-WORKTREES-01: discover_files() walked the raw
    filesystem (Path.rglob) without excluding .claude, so any sibling agent worktree
    checked out under .claude/worktrees/<id>/ (a real, gitignored directory nested
    inside ROOT in multi-agent sessions) was scanned as if it were the repository
    itself -- writing .claude/worktrees/... prefixed paths into the committed
    capabilities/registry/capabilities.json and failing capability_registry_guard.py
    plus tests/architecture/test_capability_traceability.py on the next CI run."""
    module = _load_module()
    registry, generated = _minimal_repo(tmp_path)
    _configure(module, tmp_path, registry, generated)

    worktree_test = tmp_path / ".claude/worktrees/agent-fake123/tests/test_tenant_auth.py"
    worktree_test.parent.mkdir(parents=True)
    worktree_test.write_text("def test_tenant_auth(): pass\n", encoding="utf-8")

    discovered = module.discover_files()
    assert not any(p.startswith(".claude/") for p in discovered), (
        f".claude paths leaked into discover_files(): "
        f"{[p for p in discovered if p.startswith('.claude/')]}"
    )

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply"])
    assert module.main() == 0
    capability = json.loads(registry.read_text(encoding="utf-8"))["capabilities"][0]
    assert capability["tests"] == ["tests/test_tenant_auth.py"], capability["tests"]


def test_discovery_and_candidates_are_stable_when_filesystem_order_changes(monkeypatch, tmp_path):
    module = _load_module()
    registry, generated = _minimal_repo(tmp_path)
    _configure(module, tmp_path, registry, generated)

    # الملفّات أدناه ليست زينة. الصيغة السابقة كتبت ملفّاً واحداً
    # (`services/auth/tenant_auth.py`) وكانت **تمرّ بحذف الفرزين معاً** — أي أنّها لم
    # تحرس شيئاً. السبب مقيس: ذلك الملفّ يقع في `evidence_paths` لا في `candidates`،
    # فبقيت المرشّحات ثلاثة بأنواع متمايزة (service · api · test)، ولا تبديل يستطيع
    # إعادة ترتيب ثلاثة عناصر لا يتكرّر فيها مفتاح الفرز. حارسٌ على مجموعة أصغر من
    # أن تنكشف فيها العلّة أخضرُ دائماً — وهو صنف «التكذيب الفاشل» نفسه الذي يحذّر
    # منه سجلّ القرارات. تُوسَّع العيّنة حتّى تصير المرشّحات المُشتقّة من ملفّات أكثر
    # من واحدة، فيصبح للترتيب معنى.
    #
    # الحدّ المقيس بعد التوسيع (تكذيب بالاتّجاهات الثلاثة): حذف الفرزين معاً ⇒
    # **يفشل**؛ حذف أحدهما وحده ⇒ يمرّ، ومروره صحيح لا ثغرة — فكلّ فرز يكفي وحده
    # لتحقيق الخاصّيّة، والمحروس هو «المخرَج مستقلّ عن الترتيب» لا «هذا السطر موجود».
    # فقدان التكرار الاحتياطيّ ليس فقدان الحتميّة، ولا يُدَّعى أنّ هذا يمسكه.
    for i in range(4):
        extra_test = tmp_path / f"tests/test_tenant_auth_{i}.py"
        extra_test.write_text(f"def test_tenant_auth_{i}(): pass\n", encoding="utf-8")
    ui_dir = tmp_path / "frontend/web"
    ui_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (ui_dir / f"tenantAuth{i}.tsx").write_text(
            "export const TenantAuth = () => null;\n", encoding="utf-8"
        )
    extra = tmp_path / "services/auth/tenant_auth.py"
    extra.write_text("# auth tenant implementation\n", encoding="utf-8")

    original_rglob = Path.rglob

    def reversed_rglob(self: Path, pattern: str):
        return iter(reversed(list(original_rglob(self, pattern))))

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply"])
    assert module.main() == 0
    first_registry = registry.read_bytes()
    first_candidates = (generated / "capability_link_candidates.csv").read_bytes()

    monkeypatch.setattr(Path, "rglob", reversed_rglob)
    assert module.main() == 0
    assert registry.read_bytes() == first_registry
    assert (generated / "capability_link_candidates.csv").read_bytes() == first_candidates


def test_the_committed_candidates_csv_is_in_canonical_order():
    """المصنوعة المُلتزَمة مفروزة بمحتواها — حارسٌ على الملفّ لا على الدالّة.

    الاختبار أعلاه يحرس المولّد عبر عيّنة؛ وهذا يحرس **ما دخل المستودع فعلاً**.
    الفرق ليس تكراراً: عيّنة تصغر يوماً تُبطِل الأوّل صامتاً (وقد حدث)، بينما هذا
    يقيس المصنوعة الحقيقيّة بألف صفّ وبضع مئات — لا يمكن أن يصير فارغاً بالصدفة.
    ويلتقط أيضاً مساراً لا يمرّ بالمولّد أصلاً: مصنوعة أُعيد توليدها بأداة أو فرع
    قديم ثمّ التُزِمت.
    """
    import csv

    root = Path(__file__).resolve().parents[2]
    path = root / "capabilities" / "generated" / "capability_link_candidates.csv"
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert len(rows) > 100, f"المصنوعة أصغر من أن تكشف ترتيباً ({len(rows)} صفّاً)"

    def key(row: dict) -> tuple:
        return (
            row["capability_id"],
            row["kind"],
            row["value"],
            int(row["score"]),
            row["decision"],
        )

    assert [key(r) for r in rows] == sorted(key(r) for r in rows), (
        "capability_link_candidates.csv غير مفروز بمحتواه — أُعيد توليده بترتيب "
        "مورَّث من نظام الملفّات، فسيقول `--check` «انحراف» على عدّاء آخر."
    )


def test_registry_evidence_truncation_is_declared_not_silent() -> None:
    """CAPABILITY-EVIDENCE-LISTS-TRUNCATE-SILENTLY-01 — شقّ **سجلّ الحقيقة**.

    #860 أعلن الاقتطاع في الخريطة وترك الرابط. والرابط أشدّ لأنّه يكتب
    ``capabilities/registry/capabilities.json`` نفسه، وقصُّه **أبجديّ** — فبقاء
    الشاهد كان تقرّره صدفةُ اسم الملفّ. المقيس وقتَ الاكتشاف: **٤٩٤** شاهداً
    محذوفاً صامتاً عبر ثمانِ قدرات (FM-003 وحدها ٢٠٠ واجهة و٩٦ اختباراً).

    يُقاس هنا على السجلّ المشحون: كلّ بُعدٍ **بالغٍ سقفَه** يجب أن يحمل إعلاناً
    باسمه وعدده، وكلّ إعلانٍ يجب أن يقابله بُعدٌ عند سقفه فعلاً (لا إعلان كاذب).
    """
    caps = json.loads(
        (ROOT / "capabilities/registry/capabilities.json").read_text(encoding="utf-8")
    )
    rows = caps["capabilities"] if isinstance(caps, dict) else caps
    limits = {
        "services": 8,
        "apis": 40,
        "tests": 25,
        "ui_consumers": 20,
        "mobile_consumers": 20,
    }

    at_cap_without_declaration: list[str] = []
    declared_without_cap: list[str] = []
    for row in rows:
        cid = row.get("id")
        declared = row.get("evidence_truncated") or {}
        for dim, limit in limits.items():
            n = len(row.get(dim) or [])
            if n >= limit and dim not in declared:
                at_cap_without_declaration.append(f"{cid}.{dim} ({n}/{limit})")
            if dim in declared and n < limit:
                declared_without_cap.append(f"{cid}.{dim} ({n}/{limit})")
        for dim, dropped in declared.items():
            assert int(dropped) >= 1, f"{cid}.{dim}: إعلانُ قصٍّ بصفرٍ محذوف"

    assert not at_cap_without_declaration, (
        "أبعادٌ بلغت سقفها في سجلّ الحقيقة بلا إعلان قصّ — عاد الاقتطاع الصامت: "
        f"{at_cap_without_declaration}"
    )
    assert not declared_without_cap, (
        f"إعلانُ قصٍّ لبُعدٍ لم يبلغ سقفه — إعلانٌ كاذب: {declared_without_cap}"
    )


def test_the_declaration_field_is_allowed_by_the_registry_schema() -> None:
    """حقلٌ يكتبه الرابط ويرفضه المخطَّط = بوّابةٌ حمراء لا صدقٌ مُعلَن.

    المخطَّط ``additionalProperties: false`` على القدرة، فالإعلان لا يعيش بلا
    تصريحٍ فيه — وهذا الاختبار يربط الكاتب بالعقد بدل تركهما ينحرفان.
    """
    schema = json.loads(
        (ROOT / "capabilities/schema/capability-registry.schema.json").read_text(encoding="utf-8")
    )
    props = schema["$defs"]["capability"]["properties"]
    assert "evidence_truncated" in props, "الرابط يكتب حقلاً لا يُصرّح به المخطَّط"
    assert props["evidence_truncated"]["additionalProperties"]["type"] == "integer"

"""مولّدُ جرد `main` — عقدُه أنّ **المجهول يبقى مجهولاً**، وأنّه قابلٌ لإعادة الإنتاج.

``AN-UNMEASURED-SURFACE-SERIALISED-AS-AN-EMPTY-LIST-READS-AS-NO-RELATIONS-01``.
كان المولّدُ يكتب عشرةَ أسطحٍ `[]` عارية. والنيّةُ صادقة — «لم نُقَس بعد» — لكنّ
**الشكلَ لا يحملها**: ملفٌّ محتواه `[]` يقرؤه كلُّ مستهلكٍ لاحقٍ «لا علاقات». وهو
صنفُ «الغيابُ يُقرأ قياساً» الذي يطارده هذا المستودع في كلّ حارس.

وكان المولّدُ كذلك **بلا اختبارٍ واحد**: يُشغَّل بيدٍ، ومخرجاتُه تحت `artifacts/`
المُتجاهَلة. فوجودُه لا يُثبِت أنّه يقيس، ولا أنّ تشغيلَين يتّفقان، ولا أنّ تغيّرَ
علاقةٍ حقيقيّةٍ يظهر فيه — وهي الخواصُّ الثلاثُ التي يفرضها هذا الملفّ.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/diagnostics/build_main_inventory.py"

_SPEC = importlib.util.spec_from_file_location("build_main_inventory", GENERATOR)
inventory = importlib.util.module_from_spec(_SPEC)
sys.modules["build_main_inventory"] = inventory
assert _SPEC.loader is not None
_SPEC.loader.exec_module(inventory)

_CSV_HEADER = (
    "component_id,component_kind,domain,authority_kind,source_path,"
    "deployment_units,aliases,compose_services,tables_owned,wired,tested\n"
)
_CSV_ROW = "svc-a,service,soil,owner,services/svc-a,svc-a,,svc-a,3,True,False\n"


def _fixture_tree(tmp_path: Path, *, consumers: list[str]) -> Path:
    """شجرةٌ صغيرةٌ بمُدخَلَي المولّد الحقيقيَّين، لا محاكاةٌ لمخرجاته."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "component_inventory.generated.csv").write_text(
        _CSV_HEADER + _CSV_ROW, encoding="utf-8"
    )
    (tmp_path / "platform_catalog.generated.json").write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "SOIL-001",
                        "owner": "svc-a",
                        "producer": "svc-a",
                        "consumers": consumers,
                        "entrypoints": ["POST /api/v1/soil"],
                        "kind": "read",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tmp_path


def _build(tmp_path: Path, monkeypatch, *, consumers: list[str], out_name: str = "out") -> Path:
    tree = _fixture_tree(tmp_path / out_name, consumers=consumers)
    monkeypatch.setattr(inventory, "ROOT", tree)
    monkeypatch.setattr(inventory, "_git_sha", lambda: "0" * 40)
    out = tree / "inventory"
    inventory.build(out)
    return out


def _load(out: Path, name: str):
    return json.loads((out / name).read_text(encoding="utf-8"))


# ── المجهول يبقى مجهولاً ────────────────────────────────────────────────────────


@pytest.mark.parametrize("surface", sorted(inventory.placeholders()))
def test_an_unmeasured_surface_is_never_a_bare_empty_list(tmp_path, monkeypatch, surface):
    """**الفرقُ بين «قِسنا فلا شيء» و«لم نقس» يجب أن يكون في البنية لا في النيّة.**

    ``measured`` + صفرُ صفوفٍ دعوى؛ و``not_measured`` + صفرُ صفوفٍ امتناعٌ عن الدعوى.
    """
    out = _build(tmp_path, monkeypatch, consumers=["svc-b"])
    payload = _load(out, surface)
    assert isinstance(payload, dict), f"{surface} عاد قائمةً عارية — «لم يُقَس» يُقرأ «لا شيء»"
    assert payload["measurement_state"] == "not_measured"
    assert payload["rows"] == [] and payload["row_count"] == 0
    assert payload["question_to_resolve"].strip()
    assert payload["candidate_sources"], "سطحٌ بلا مرشّحِ مصدرٍ لا يُوجِّه القياسَ التالي"


def test_the_manifest_states_how_many_surfaces_were_not_measured(tmp_path, monkeypatch):
    """عددٌ في الترويسة أصعبُ على الإغفال من عشرة ملفّاتٍ صامتة."""
    out = _build(tmp_path, monkeypatch, consumers=["svc-b"])
    counts = _load(out, "inventory_manifest.json")["counts"]
    assert counts["surfaces_declared"] == len(inventory.placeholders())
    assert counts["surfaces_not_measured"] == counts["surfaces_declared"]


def test_a_declared_edge_is_never_promoted_to_resolved_without_evidence(tmp_path, monkeypatch):
    """العلاقةُ المُعلَنة في الكتالوج **ليست** علاقةً محسومة.

    ٧٢٢ علاقةً معلَنةً ليست ٧٢٢ عطلاً، ولا ٧٢٢ علاقةً مثبتة. الترقيةُ تحتاج موضعَ
    استدعاءٍ مصدريّاً أو أثراً تشغيليّاً — ولا شيءَ منهما يقرؤه هذا المولّد اليوم.
    """
    out = _build(tmp_path, monkeypatch, consumers=["svc-b"])
    assert _load(out, "integration_edges.json") == []
    unresolved = _load(out, "unresolved_edges.json")
    assert [e["evidence_state"] for e in unresolved] == ["declared"]
    assert unresolved[0]["question_to_ask"].strip()


# ── قابليّةُ إعادة الإنتاج ───────────────────────────────────────────────────────


def test_two_runs_on_the_same_tree_produce_identical_bytes(tmp_path, monkeypatch):
    """**معيارُ المالك حرفيّاً:** تشغيلان على الشجرة نفسِها يُنتجان المحتوى نفسَه.

    الترتيبُ مفروضٌ في المولّد (`sort_keys` و`sorted`)؛ وهذا الشاهدُ يُثبِته بدل أن
    يفترضه — فقاموسُ بايثون يحفظ ترتيبَ الإدراج، ومصنوعٌ يتبدّل بايتُه بلا تبدّل
    معناه يُغرِق كلَّ مقارنةٍ لاحقةٍ في ضوضاء.
    """
    first = _build(tmp_path, monkeypatch, consumers=["svc-b"], out_name="a")
    second = _build(tmp_path, monkeypatch, consumers=["svc-b"], out_name="b")
    names = sorted(p.name for p in first.iterdir())
    assert names == sorted(p.name for p in second.iterdir())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_a_changed_relation_shows_up_in_the_inventory(tmp_path, monkeypatch):
    """**معيارُ المالك الثاني:** تغييرُ علاقةٍ فعليّةٍ يجب أن يظهر في الجرد.

    جردٌ لا يتحرّك حين تتحرّك الشجرةُ تحته ليس جرداً بل لقطةً مجمَّدة — وهذا هو
    الشاهدُ الذي يفرّق بينهما: مستهلكٌ يُضاف في الكتالوج يظهر حافّةً معلَنةً جديدة.
    """
    before = _load(
        _build(tmp_path, monkeypatch, consumers=["svc-b"], out_name="a"), "unresolved_edges.json"
    )
    after = _load(
        _build(tmp_path, monkeypatch, consumers=["svc-b", "svc-c"], out_name="b"),
        "unresolved_edges.json",
    )
    assert {e["to"] for e in before} == {"svc-b"}
    assert {e["to"] for e in after} == {"svc-b", "svc-c"}
    manifest = _load(tmp_path / "b" / "inventory", "inventory_manifest.json")
    assert manifest["counts"]["declared_consumer_edges_pending_resolution"] == len(after)


def test_the_manifest_pins_every_source_by_digest(tmp_path, monkeypatch):
    """نتيجةٌ بلا بصمةِ مصدرها لا تُقارَن بغيرها — والمقارنةُ هي كلُّ فائدة الجرد."""
    out = _build(tmp_path, monkeypatch, consumers=["svc-b"])
    manifest = _load(out, "inventory_manifest.json")
    assert manifest["source_sha"]
    assert {s["path"] for s in manifest["sources"]} == {
        "component_inventory.generated.csv",
        "platform_catalog.generated.json",
    }
    for source in manifest["sources"]:
        assert len(source["sha256"]) == 64


def test_the_generator_emits_no_verdict(tmp_path, monkeypatch):
    """عقدُ هذا المولّد المكتوب: **وصفٌ بلا حكم**. لا درجةَ ولا عتبةَ ولا علاجاً."""
    out = _build(tmp_path, monkeypatch, consumers=["svc-b"])
    manifest = _load(out, "inventory_manifest.json")
    assert manifest["mode"] == "descriptive"
    assert manifest["verdicts"] is False and manifest["thresholds"] is False
    assert set(manifest["evidence_semantics"]) == {"resolved", "declared", "unresolved"}


# ── سطحُ ملكيّة الكتابة: الترقيةُ بالقياس لا بالتحرير ──────────────────────────


def _ownership_tree(
    tmp_path: Path, *, contract: str | None, source: tuple[str, str] | None
) -> Path:
    """مِرقاةٌ تحمل **مُدخَلَي القياس الحقيقيَّين**: عقدٌ وملفُّ مصدرٍ يكتب.

    والمحرّكُ يُستورَد من `scripts/ci/` بمسارٍ نسبيٍّ إلى `ROOT`، فيُنسَخ إليها —
    وإلّا قاس الشاهدُ شجرةَ المستودع الحقيقيّة وهو يظنّ أنّه يقيس مِرقاته.
    """
    tree = _fixture_tree(tmp_path, consumers=["svc-b"])
    guard_src = ROOT / "scripts" / "ci" / "db_writer_ownership_guard.py"
    dest = tree / "scripts" / "ci"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "db_writer_ownership_guard.py").write_text(
        guard_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    if contract is not None:
        arch = tree / "docs" / "architecture"
        arch.mkdir(parents=True, exist_ok=True)
        (arch / "db_ownership.yml").write_text(contract, encoding="utf-8")
    if source is not None:
        rel, body = source
        target = tree / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tree


def _ownership(tmp_path: Path, monkeypatch, **kwargs):
    tree = _ownership_tree(tmp_path, **kwargs)
    monkeypatch.setattr(inventory, "ROOT", tree)
    monkeypatch.setattr(inventory, "_git_sha", lambda: "0" * 40)
    out = tree / "inventory"
    inventory.build(out)
    return _load(out, "database_ownership.json"), _load(out, "inventory_manifest.json")


def _contract_with(**tables: list[str]) -> str:
    """عقدٌ صغيرٌ بالشكل الذي يقرؤه المحرّك — ``tables:`` ثمّ جدولٌ لكلّ مفتاح.

    ``load_contract`` ترفض عقداً دون مئة جدول (حمايةٌ من صفرٍ كاذب)، فتُحشى البقيّةُ
    بجداولَ خاملة: الحشوُ يُرضي شرطَ القراءة ولا يُدخِل حافّةً في المقيس.
    """
    lines = ["tables:"]
    for name, writers in tables.items():
        lines += [f"  {name}:", f"    owner: {writers[0]}", f"    writers: [{', '.join(writers)}]"]
    for index in range(200):
        lines += [f"  filler_{index}:", "    owner: nobody", "    writers: [nobody]"]
    return "\n".join(lines) + "\n"


def test_the_ownership_surface_stays_unmeasured_without_a_contract(tmp_path, monkeypatch):
    """**«الترقيةُ بالقياس لا بالتحرير» خاصّيّةٌ تُختبَر، لا جملةٌ تُقال.**

    شجرةٌ بلا عقدٍ لا تُنتِج صفوفاً، فيبقى السطحُ `not_measured` بسؤاله ومرشّحاته —
    ولو أُرجِعت صفوفٌ فارغةٌ بحالة `measured` لكان ذلك ادّعاءً بهيئة قياس.
    """
    surface, manifest = _ownership(tmp_path, monkeypatch, contract=None, source=None)
    assert surface["measurement_state"] == "not_measured"
    assert surface["rows"] == [] and surface["question_to_resolve"].strip()
    assert manifest["counts"]["surfaces_not_measured"] == manifest["counts"]["surfaces_declared"]


def test_a_write_site_the_contract_authorises_is_resolved_not_merely_declared(
    tmp_path, monkeypatch
):
    """موضعُ المصدر هو ما يرفع حافّةً من `declared` إلى `resolved` — وهو الدليلُ الذي
    كان المسحُ يلتقطه ثمّ يُسقِطه قبل هذه الشريحة."""
    surface, manifest = _ownership(
        tmp_path,
        monkeypatch,
        contract=_contract_with(widgets=["svc-a"]),
        source=("services/svc-a/store.py", 'SQL = "INSERT INTO widgets (id) VALUES (1)"\n'),
    )
    assert surface["measurement_state"] == "measured"
    row = next(r for r in surface["rows"] if r["table"] == "widgets" and r["component"] == "svc-a")
    assert row["evidence_state"] == "resolved"
    assert row["contract_state"] == "authorised"
    assert "services/svc-a/store.py" in row["sites"]
    assert manifest["counts"]["surfaces_not_measured"] < manifest["counts"]["surfaces_declared"]


def test_a_declared_writer_with_no_located_site_stays_declared(tmp_path, monkeypatch):
    """**ولا يُرقّى بالعقد وحده.** ٢١٢ من ٣٩١ حافّةً مُعلَنةً في الشجرة الحقيقيّة بلا
    موضعٍ مقيس؛ ترقيتُها بحكم الإعلان كانت ستجعل السطحَ يصف عقداً لا شجرة."""
    surface, _ = _ownership(
        tmp_path, monkeypatch, contract=_contract_with(widgets=["svc-a"]), source=None
    )
    row = next(r for r in surface["rows"] if r["table"] == "widgets")
    assert row["evidence_state"] == "declared"
    assert row["sites"] == []


def test_a_measured_write_the_contract_forbids_is_kept_not_dropped(tmp_path, monkeypatch):
    """كتابةٌ مقيسةٌ لم يأذن بها العقدُ **حافّةٌ حقيقيّة**. إسقاطُها يجعل السطحَ يصف
    ما يجب أن يكون لا ما هو كائن — وهو الصنفُ الذي وُجِد هذا الجردُ لأجله."""
    surface, _ = _ownership(
        tmp_path,
        monkeypatch,
        contract=_contract_with(widgets=["svc-a"]),
        source=("services/svc-b/rogue.py", 'SQL = "UPDATE widgets SET id = 2"\n'),
    )
    row = next(r for r in surface["rows"] if r["component"] == "svc-b")
    assert row["contract_state"] == "not_authorised"
    assert row["evidence_state"] == "resolved" and row["sites"]
    assert surface["counts"]["by_contract_state"]["not_authorised"] >= 1


def test_the_surface_carries_its_blind_spots_inside_the_artifact(tmp_path, monkeypatch):
    """حدُّ الأداة حقلٌ يُقرأ لا تعليقٌ بجانبها — وهذا هو درسُ هذا السطح بعينه.

    بلا ذلك يُقرأ `declared` نفياً لوجود كاتب، وهو أخطرُ من `[]` العارية لأنّه يحمل
    هيئةَ القياس.
    """
    surface, _ = _ownership(
        tmp_path,
        monkeypatch,
        contract=_contract_with(widgets=["svc-a"]),
        source=("services/svc-a/store.py", 'SQL = "INSERT INTO widgets (id) VALUES (1)"\n'),
    )
    assert surface["blind_spots_ar"], "سطحٌ مقيسٌ بلا حدودٍ مُعلَنة يُقرأ أوسعَ ممّا قاس"
    assert any(".sql" in line for line in surface["blind_spots_ar"])
    assert surface["what_this_does_not_claim_ar"].strip()


def test_the_surface_names_the_blocking_engine_and_adds_no_second_scanner():
    """محرّكان يُجيبان سؤالاً واحداً ينحرفان بصمت — الصنفُ المُسجَّل في هذا المستودع.

    فالسطحُ يُسمّي المحرّكَ الحاجب، **ولا يُعيد تعريف نمطِ الكتابة** هنا.
    """
    source = (ROOT / "scripts/diagnostics/build_main_inventory.py").read_text(encoding="utf-8")
    assert "db_writer_ownership_guard.py" in source
    for token in ("INSERT\\s+INTO", "DELETE\\s+FROM", "INSERT INTO"):
        assert token not in source, f"ماسحٌ ثانٍ للكتابة داخل الجرد: {token!r}"

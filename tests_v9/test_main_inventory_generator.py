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


#: السطحُ الوحيد الذي خرج من «لم يُقَس» لأنّه قِيس — ويُستثنى بالاسم لا بالصمت،
#: كي يُحمِّر هذا الملفُّ إن رُقِّي سطحٌ آخر بلا مقياسٍ يُنتِج صفوفَه.
_MEASURED_SURFACES = {"frontend_consumers.json"}


@pytest.mark.parametrize("surface", sorted(set(inventory.placeholders()) - _MEASURED_SURFACES))
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
    assert counts["surfaces_not_measured"] == counts["surfaces_declared"] - len(
        _MEASURED_SURFACES
    ), "عددُ غيرِ المقيس لا يطابق ما أُعلِن مقيساً — رُقِّي سطحٌ بلا إعلان"


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
    # **والمقيسُ سطحي وحدَه، لا «كلُّ الأسطح».** كانت هذه الحالةُ تشترط
    # `not_measured == declared` — وهو ثابتٌ صحيحٌ **بالمصادفة** يوم كانت العشرةُ كلُّها
    # غيرَ مقيسة، ويصير خاطئاً يومَ يُرقّي أحدٌ سطحاً آخر. وقد وقع ذلك فعلاً: ترقيةُ
    # `frontend_consumers` في #1044 تقع على هذه المِرقاة، فاحمرّت الحالةُ عند الدمج
    # وهي تصف عملاً صحيحاً — أي «بوّابةٌ لا تُغلَق بعملٍ صحيح».
    assert manifest["counts"]["surfaces_not_measured"] >= 1
    assert manifest["counts"]["surfaces_declared"] >= manifest["counts"]["surfaces_not_measured"]


def test_a_write_site_the_contract_authorises_is_resolved_not_merely_declared(
    tmp_path, monkeypatch
):
    """موضعُ المصدر هو ما يرفع حافّةً من `declared` إلى `resolved` — وهو الدليلُ الذي
    كان المسحُ يلتقطه ثمّ يُسقِطه قبل هذه الشريحة."""
    surface, manifest = _ownership(
        tmp_path,
        monkeypatch,
        contract=_contract_with(widgets=["svc-a"]),
        source=("services/svc-a/store.py", 'import asyncpg\nSQL = "INSERT INTO widgets (id) VALUES (1)"\n'),
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
        source=("services/svc-b/rogue.py", 'import asyncpg\nSQL = "UPDATE widgets SET id = 2"\n'),
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
        source=("services/svc-a/store.py", 'import asyncpg\nSQL = "INSERT INTO widgets (id) VALUES (1)"\n'),
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


# ── حسمُ الحوافّ إلى أدلّةِ مصدر — البند ١د ───────────────────────────────────────


def test_a_resolved_edge_carries_its_whole_evidence_chain(tmp_path, monkeypatch):
    """**الترقيةُ تحتاج سلسلةً كاملة، ودليلُها يسمّي سطرَ كلِّ خطوة.**

    حافّةٌ تُرقّى بلا موضع نداءٍ ولا قاعدةِ بوّابة دعوى لا قياس — وهذا الشاهدُ
    يمنع أن يصير `resolved` وسماً يُكتب بدل أن يُشتقّ.
    """
    out = _build(tmp_path, monkeypatch, consumers=["svc-b"])
    for edge in _load(out, "integration_edges.json"):
        evidence = edge["evidence"]
        assert edge["evidence_state"] == "resolved"
        assert edge["resolved_entrypoint"]
        for anchor in ("call_site", "client_binding", "endpoint_binding", "gateway_rule"):
            assert ":" in evidence[anchor], f"{anchor} بلا سطر"


def test_the_manifest_declares_the_scanner_blind_spot(tmp_path, monkeypatch):
    """**حدُّ الأداة يُصدَّر مع نتيجتها.**

    ماسحٌ ساكنٌ لا يرى مساراً يُبنى في وقت التشغيل. فعددُ ما لا يراه يُعلَن، وإلّا
    قرأ القارئُ «ما لم يُحسَم غيرُ موجود» — وهو بعينه العطل الذي وُجِد هذا الجرد
    ليمنعه.
    """
    out = _build(tmp_path, monkeypatch, consumers=["svc-b"])
    resolution = _load(out, "inventory_manifest.json")["edge_resolution"]
    for field in ("resolved", "still_unresolved", "scanner_blind_spots", "gateway_rules"):
        assert field in resolution
    assert resolution["gateway_upstreams_unmapped"] == 0, (
        "مُجرىً أعلى بلا مكوّنٍ مطابق — الخريطةُ تنحرف عن جرد المكوّنات"
    )


def test_the_live_tree_resolves_edges_with_evidence():
    """**الزرعُ الحيّ على الشجرة الحقيقيّة، لا على تركيبةٍ صغيرة.**

    شجرةُ الاختبار لا تحمل `nginx.conf` ولا واجهةً، فتُنتِج صفرَ حوافّ محسومة —
    وهو سلوكٌ صحيح لكنّه لا يُثبِت أنّ السلسلة تعمل. هذا يقيسها على الشجرة نفسِها.
    """
    components = json.loads(
        (ROOT / "component_inventory.generated.csv").read_text(encoding="utf-8")[:0] or "[]"
    )
    del components
    module = inventory._resolver()
    real = inventory.load_components()
    _, declared = inventory.integration_edges(inventory.load_capabilities())
    resolved, remaining, report = module.resolve(declared, real, ROOT)
    assert resolved, "لم تُحسَم حافّةٌ واحدة على الشجرة الحيّة — السلسلةُ منقطعة"
    assert report["gateway_upstreams_unmapped"] == 0
    assert len(resolved) + len(remaining) == len(declared), "حافّةٌ ضاعت بين القائمتين"


# ── سطحُ المسارات: مقيسٌ بالمحرّك الحاجب نفسِه ──────────────────────────────────


_ROUTER_BODY = """from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.post("/api/v1/fields")
def create_field():
    return {}
"""

_SECOND_ROUTER_BODY = """from fastapi import APIRouter

other = APIRouter()


@other.post("/api/v1/fields")
def create_field_again():
    return {}
"""


def _routes_tree(
    tmp_path: Path,
    *,
    extraction: dict | None,
    placement: dict | None = None,
    second_module: bool = False,
    break_engine: bool = False,
) -> Path:
    """مِرقاةٌ تحمل مُدخَلَي القياس الحقيقيَّين: راوترٌ يُعلِن، وخريطةٌ تُسمّي المالك.

    والمحرّكُ يُنسَخ إلى `scripts/ci/` لأنّه يُحمَّل بمسارٍ نسبيٍّ إلى `ROOT` — وإلّا
    قاس الشاهدُ شجرةَ المستودع وهو يظنّ أنّه يقيس مِرقاته.
    """
    tree = _fixture_tree(tmp_path, consumers=["svc-b"])
    dest = tree / "scripts" / "ci"
    dest.mkdir(parents=True, exist_ok=True)
    engine_src = ROOT / "scripts" / "ci" / "platform_route_classification.py"
    body = engine_src.read_text(encoding="utf-8")
    if break_engine:
        body = "raise RuntimeError('محرّكٌ قائمٌ لا يُحمَّل')\n" + body
    (dest / "platform_route_classification.py").write_text(body, encoding="utf-8")

    api = tree / "services" / "sahool-platform" / "api" / "routers"
    api.mkdir(parents=True, exist_ok=True)
    (api / "platform_health.py").write_text(_ROUTER_BODY, encoding="utf-8")
    if second_module:
        (api / "legacy_fields.py").write_text(_SECOND_ROUTER_BODY, encoding="utf-8")

    arch = tree / "docs" / "architecture"
    arch.mkdir(parents=True, exist_ok=True)
    if extraction is not None:
        (arch / "platform_extraction_map.json").write_text(
            json.dumps(extraction, ensure_ascii=False), encoding="utf-8"
        )
    if placement is not None:
        (arch / "platform_route_placement_contract.json").write_text(
            json.dumps(placement, ensure_ascii=False), encoding="utf-8"
        )
    return tree


def _routes(tmp_path: Path, monkeypatch, **kwargs):
    tree = _routes_tree(tmp_path, **kwargs)
    monkeypatch.setattr(inventory, "ROOT", tree)
    monkeypatch.setattr(inventory, "_git_sha", lambda: "0" * 40)
    out = tree / "inventory"
    inventory.build(out)
    return _load(out, "routes.json"), _load(out, "inventory_manifest.json")


_OWNED = {"routes": [{"method": "POST", "path": "/api/v1/fields", "target_owner": "field-svc"}]}


def test_the_routes_surface_stays_unmeasured_without_the_extraction_map(tmp_path, monkeypatch):
    """**الترقيةُ بالقياس لا بالتحرير** — والسؤالُ ثلاثيٌّ فلا يُجاب بثُلثيه.

    السطحُ يسأل «أين يُعلَن · **ومن يملكه** · ونطاقٌ أم بنية». وبلا الخريطة يبقى
    المالكُ مجهولاً، فإعلانُ `measured` كان سيقول إنّ السؤالَ حُسِم وثُلثُه لم يُطرَح.
    """
    surface, _ = _routes(tmp_path, monkeypatch, extraction=None)
    assert surface["measurement_state"] == "not_measured"
    assert surface["rows"] == [] and surface["question_to_resolve"].strip()
    assert surface["candidate_sources"]


def test_an_engine_that_exists_but_cannot_load_fails_loudly_not_as_not_measured(
    tmp_path, monkeypatch
):
    """`AN-ENGINE-THAT-FAILS-TO-LOAD-IS-REPORTED-AS-AN-ABSENT-MEASURE-01`.

    **العطلُ وقع في بناء هذه الشريحة نفسِها:** `except Exception: return None` ابتلع
    خطأَ تحميلٍ حقيقيّاً (`@dataclass` يقرأ `sys.modules[cls.__module__]`، فسقط
    التحميلُ قبل تسجيل الوحدة)، فأبلغ الجردُ `not_measured` **بهيئة امتناعٍ صادق**
    بينما المحرّكُ قائمٌ في الشجرة ويحجب في CI.

    فالغيابُ يُرجِع `None`، وأمّا العطبُ فيفشل صراحةً — وإلّا صار «لم يُقَس» مخبأً
    لكلّ عطلٍ في المحرّك.
    """
    with pytest.raises(SystemExit) as excinfo:
        _routes(tmp_path, monkeypatch, extraction=_OWNED, break_engine=True)
    assert "ENGINE_UNLOADABLE" in str(excinfo.value)


def test_a_route_is_classified_by_the_blocking_engine_not_by_a_local_list(tmp_path, monkeypatch):
    """قائمةُ بنيةٍ ثانيةٌ هنا كانت ستنحرف عن التي تُقاس عليها الميزانيّة.

    و`/healthz` بنيةٌ بحكم المحرّك وحدَه؛ وسطرٌ عاديٌّ يبقى نطاقاً.
    """
    surface, _ = _routes(tmp_path, monkeypatch, extraction=_OWNED)
    assert surface["measurement_state"] == "measured"
    kinds = {(r["method"], r["path"]): r["kind"] for r in surface["rows"]}
    assert kinds[("GET", "/healthz")] == "infrastructure"
    assert kinds[("POST", "/api/v1/fields")] == "domain"
    assert surface["counts"]["infrastructure"] == 1
    assert surface["counts"]["domain"] == 1


def test_a_declared_owner_is_never_recorded_as_a_measured_site(tmp_path, monkeypatch):
    """**طبقتا الدليل لا تُدمَجان.**

    موضعُ الإعلان مقيس (`resolved`)، وأمّا المالكُ فسجلٌّ يصف البنيةَ المقصودة
    (`declared`). ودمجُهما كان سيُنتِج «مساراتٍ مملوكةً» تُقرأ محقَّقةً.
    """
    surface, _ = _routes(tmp_path, monkeypatch, extraction=_OWNED)
    row = next(r for r in surface["rows"] if r["path"] == "/api/v1/fields")
    # الموضعُ يُفحَص **خاصّيّةً**: ملفٌّ يحمل الإعلان وسطرٌ يقع داخله. وتثبيتُ رقمٍ
    # بعينه كان يُثبّت صياغةَ المِرقاة لا السلوك (`GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`)
    # — وقد أخطأتُ الرقمَ فعلاً في أوّل صياغة.
    assert row["evidence_state"] == "resolved"
    file_part, _, line_part = row["site"].rpartition(":")
    assert file_part.endswith("api/routers/platform_health.py")
    assert line_part.isdigit() and int(line_part) > 0
    assert row["owner"] == "field-svc"
    assert row["owner_evidence_state"] == "declared"


def test_a_route_absent_from_the_map_is_unmapped_not_silently_dropped(tmp_path, monkeypatch):
    """إسقاطُ ما لا تعرفه الخريطةُ يجعل السطحَ يصف الخريطةَ لا الشجرة."""
    surface, _ = _routes(tmp_path, monkeypatch, extraction=_OWNED)
    health = next(r for r in surface["rows"] if r["path"] == "/healthz")
    assert health["owner"] is None and health["owner_evidence_state"] == "unmapped"
    assert surface["counts"]["unmapped_owner"] == 1
    assert surface["counts"]["declarations"] == 2


def test_declarations_and_unique_keys_are_counted_apart(tmp_path, monkeypatch):
    """مفتاحٌ يتكرّر عبر وحدتين ليس تصادماً بالضرورة — والعددان يختلفان فعلاً.

    البادئاتُ غيرُ محلولة، فدمجُ العددين كان سيُخفي أنّ «عددَ المسارات» عددُ
    **إعلانات**. وهو الفرقُ الذي يقع على الشجرة الحيّة لا في المِرقاة وحدَها.
    """
    surface, _ = _routes(tmp_path, monkeypatch, extraction=_OWNED, second_module=True)
    assert surface["counts"]["declarations"] == 3
    assert surface["counts"]["unique_method_path_keys"] == 2


def test_the_placement_contract_says_where_an_infrastructure_route_belongs(tmp_path, monkeypatch):
    """التصنيفُ يقول ما هو المسار؛ وخريطةُ الموضع تقول أين ينتمي — ولا تُخلَطان."""
    contract = {
        "routes": [
            {
                "method": "GET",
                "path": "/healthz",
                "required_source": "services/sahool-platform/api/routers/platform_health.py",
            }
        ]
    }
    surface, _ = _routes(tmp_path, monkeypatch, extraction=_OWNED, placement=contract)
    health = next(r for r in surface["rows"] if r["path"] == "/healthz")
    assert health["placement_state"] == "at_required_source"

    contract["routes"][0]["required_source"] = "services/sahool-platform/api/main.py"
    surface, _ = _routes(tmp_path / "moved", monkeypatch, extraction=_OWNED, placement=contract)
    health = next(r for r in surface["rows"] if r["path"] == "/healthz")
    assert health["placement_state"] == "elsewhere"


def test_the_routes_surface_carries_its_blind_spots_inside_the_artifact(tmp_path, monkeypatch):
    """حدُّ الأداة حقلٌ يُقرأ — القارئُ الآليُّ لا يقرأ التعليقات."""
    surface, _ = _routes(tmp_path, monkeypatch, extraction=_OWNED)
    blind = " ".join(surface["blind_spots_ar"])
    assert "include_router" in blind, "الحدُّ الأخطر (البادئاتُ غيرُ محلولة) غيرُ محمول"
    assert "sahool-platform" in blind, "لم يُعلَن أنّ المسحَ على خدمةٍ واحدة"
    assert surface["what_this_does_not_claim_ar"].strip()
    assert surface["engine"] == "scripts/ci/platform_route_classification.py"


def test_the_generator_defines_no_second_route_scanner():
    """ماسحٌ ثانٍ يُنتِج جواباً ثانياً عن سؤالٍ واحد — ويُقاس عليه الأوّل في بوّابة."""
    source = GENERATOR.read_text(encoding="utf-8")
    assert "platform_route_classification" in source
    for pattern in ('"/healthz"', "HTTP_METHODS", "ast.Call"):
        assert pattern not in source, f"الجردُ يُعرّف تصنيفَ مسارٍ بنفسه: {pattern}"


def test_the_live_tree_measures_routes_with_the_same_engine_the_budget_uses():
    """**الزرعُ الحيّ:** جردٌ وبوّابةٌ يعدّان الشيءَ نفسَه، فيجب أن يتطابقا."""
    surface = inventory.routes_surface()
    assert surface is not None, "الشجرةُ الحيّة تحمل المحرّكَ والخريطة ولم تُقَس"
    engine = inventory._route_engine()
    infrastructure, domain = engine.partition_routes(
        engine.collect_platform_routes(ROOT / "services" / "sahool-platform")
    )
    assert surface["counts"]["domain"] == len(domain)
    assert surface["counts"]["infrastructure"] == len(infrastructure)
    assert surface["counts"]["declarations"] == len(domain) + len(infrastructure)

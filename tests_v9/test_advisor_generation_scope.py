"""The advisor asks the approval gate with the question's crop and region (F6 follow-up).

``partition_generation_references`` admits an approved excerpt only when its applicability
matches the question's crop and region. The advisor called it with neither, so every excerpt
was held as ``question_crop_unknown`` even after an agronomist approved it. The scope follows
the rule retrieval already uses: a field question takes the crop from the owner's crop card,
never from the client. Its region comes from the same owner read: the platform's AI context
pack carries the field row as ``field_profile``, so ``fields.region`` is the field's region. A
client-sent region is ignored for a field question, and a field whose record has no region keeps
the region unknown. A general question has no owner record, so the client's crop and region are
its only scope.
"""

from __future__ import annotations

import ast
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADVISOR = ROOT / "services" / "ai_agronomist"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import ai_evidence_runtime as runtime  # noqa: E402
from shared.ai.reference_approvals import content_digest, index_approvals  # noqa: E402
from shared.ai.seed_claims import partition_generation_references  # noqa: E402

pytestmark = pytest.mark.unit

TEXT = "placeholder excerpt used only by this test"
REVISION = "unit-rev-1"
ON = date(2026, 6, 1)


def _approvals():
    record = {
        "approval_id": f"unit-{content_digest(TEXT)[:12]}-{REVISION}",
        "content_digest": content_digest(TEXT),
        "source_revision": REVISION,
        "source": {
            "title": "unit fixture source",
            "publisher": "unit fixture publisher",
            "publication_date": "2025-01-15",
        },
        "reviewer": {"name": "Unit Reviewer", "identity": "unit-registry-0001"},
        "reviewed_on": "2026-01-10",
        "valid_until": "2026-12-31",
        "applicability": {
            "crops": ["unit-crop"],
            "regions": ["unit-region"],
            "jurisdiction": "unit-jurisdiction",
        },
    }
    manifest = {
        "schema": "sahool.reference_approval_manifest",
        "schema_version": 1,
        "approvals": [record],
    }
    return index_approvals(manifest)


def _excerpt():
    return {"chunk_id": "c-1", "text": TEXT, "source_revision": REVISION}


def _partition(req, retrieval_crop, owner_region=None):
    scope = runtime._generation_scope(req, retrieval_crop, owner_region)
    return partition_generation_references([_excerpt()], approvals=_approvals(), as_of=ON, **scope)


def test_general_question_scope_admits_an_excerpt_approved_for_its_crop_and_region():
    req = SimpleNamespace(field_id=None, crop="unit-crop", region="unit-region")
    usable, held = _partition(req, retrieval_crop="unit-crop")
    assert [u["chunk_id"] for u in usable] == ["c-1"] and held == []


_ABSENT = object()


def _owner_field_state(region):
    """The shape ``_fetch_canonical_field_state`` returns: canonical state + owner pack."""
    profile = {"field_id": "f-1", "crop": "unit-crop"}
    if region is not _ABSENT:
        profile["region"] = region
    return {
        "schema_version": "canonical_field_state.v1",
        "field_id": "f-1",
        "ai_context_pack": {"field_id": "f-1", "tenant_id": "t-1", "field_profile": profile},
    }


def _field_scope(req, field_state, retrieval_crop="unit-crop"):
    owner_region = runtime._trusted_region_for_generation(field_state, req.field_id, "t-1")
    return runtime._generation_scope(req, retrieval_crop, owner_region), owner_region


def test_field_question_passes_the_owner_region_to_the_gate():
    req = SimpleNamespace(field_id="f-1", crop="client-crop", region=None)
    scope, owner_region = _field_scope(req, _owner_field_state("  unit-region "))
    assert owner_region == "unit-region"
    assert scope == {"crop": "unit-crop", "region": "unit-region"}
    usable, held = _partition(req, retrieval_crop="unit-crop", owner_region=owner_region)
    assert [u["chunk_id"] for u in usable] == ["c-1"] and held == []


@pytest.mark.parametrize("region", [_ABSENT, None, "", "   ", 7, ["unit-region"]])
def test_field_question_without_an_owner_region_has_no_region(region):
    req = SimpleNamespace(field_id="f-1", crop="unit-crop", region=None)
    scope, owner_region = _field_scope(req, _owner_field_state(region))
    assert owner_region is None
    assert scope == {"crop": "unit-crop", "region": None}
    usable, held = _partition(req, retrieval_crop="unit-crop", owner_region=owner_region)
    assert usable == []
    assert [h["generation_hold_reason"] for h in held] == ["question_region_unknown"]


@pytest.mark.parametrize("field_state", [None, {}, {"ai_context_pack": "not-a-pack"}])
def test_field_question_without_an_owner_pack_has_no_region(field_state):
    req = SimpleNamespace(field_id="f-1", crop="unit-crop", region="unit-region")
    scope, owner_region = _field_scope(req, field_state)
    assert owner_region is None and scope["region"] is None


def test_a_client_region_is_ignored_for_a_field_question():
    # The owner record names another region; the client claims the approved one.
    req = SimpleNamespace(field_id="f-1", crop="unit-crop", region="unit-region")
    scope, owner_region = _field_scope(req, _owner_field_state("owner-region"))
    assert scope == {"crop": "unit-crop", "region": "owner-region"}
    usable, held = _partition(req, retrieval_crop="unit-crop", owner_region=owner_region)
    assert usable == []
    assert [h["generation_hold_reason"] for h in held] == ["region_not_applicable"]


def test_a_general_question_ignores_any_owner_region():
    req = SimpleNamespace(field_id=None, crop="unit-crop", region="unit-region")
    assert (
        runtime._trusted_region_for_generation(_owner_field_state("owner-region"), None, "t-1")
        is None
    )
    assert runtime._generation_scope(req, "unit-crop", None) == {
        "crop": "unit-crop",
        "region": "unit-region",
    }


def test_field_question_takes_the_owner_crop_and_never_the_client_region():
    req = SimpleNamespace(field_id="f-1", crop="client-crop", region="unit-region")
    assert runtime._generation_scope(req, "unit-crop") == {"crop": "unit-crop", "region": None}
    usable, held = _partition(req, retrieval_crop="unit-crop")
    assert usable == []
    assert [h["generation_hold_reason"] for h in held] == ["question_region_unknown"]


def test_field_question_without_an_owner_crop_card_has_no_crop():
    req = SimpleNamespace(field_id="f-1", crop="unit-crop", region="unit-region")
    assert runtime._generation_scope(req, None) == {"crop": None, "region": None}
    usable, held = _partition(req, retrieval_crop=None)
    assert usable == []
    assert [h["generation_hold_reason"] for h in held] == ["question_crop_unknown"]


def test_a_blank_client_region_is_no_region():
    req = SimpleNamespace(field_id=None, crop="unit-crop", region="  ")
    assert runtime._generation_scope(req, "unit-crop") == {"crop": "unit-crop", "region": None}


def test_the_advisor_passes_that_scope_to_the_approval_gate():
    tree = ast.parse((ADVISOR / "ai_evidence_runtime.py").read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "partition_generation_references"
    ]
    assert len(calls) == 1, "one approval gate on the advisor path"
    (call,) = calls
    assert [ast.unparse(k) for k in call.keywords] == [
        "**_generation_scope(req, retrieval_crop, retrieval_region)"
    ]
    # The region handed to the gate is the owner read, computed from the fetched field state.
    assigns = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["retrieval_region"]
    ]
    assert [ast.unparse(a.value) for a in assigns] == [
        "_trusted_region_for_generation(field_state, req.field_id, tenant_id)"
    ]


# ── Owner side: the platform pack carries ``fields.region`` in ``field_profile`` ──────────

_PLATFORM = str(ROOT / "services" / "sahool-platform")
_PLATFORM_ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "field_ai_context.py"


def _field_ai_context():
    if _PLATFORM not in sys.path:
        sys.path.insert(0, _PLATFORM)
    pytest.importorskip("fastapi")
    from api.routers import field_ai_context  # noqa: PLC0415

    return field_ai_context


def test_the_owner_pack_reads_the_whole_field_row_so_region_reaches_field_profile():
    # ``field_profile`` is the whole ``fields`` row; narrowing that select would drop the
    # region the advisor relies on. Read from source: no database or connection stand-in.
    src = (_PLATFORM_ROUTER).read_text(encoding="utf-8")
    fn = next(
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_fetch_field_profile"
    )
    sql = [
        c.value
        for c in ast.walk(fn)
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and "SELECT" in c.value
    ]
    assert len(sql) == 1 and "to_jsonb(f.*)" in sql[0] and "FROM fields f" in sql[0], sql
    region_columns = [
        ROOT / "migrations" / "v33_fields_extended.sql",
        ROOT / "migrations" / "v104_fields_create_contract.sql",
    ]
    for migration in region_columns:
        text = migration.read_text(encoding="utf-8")
        assert "ALTER TABLE fields ADD COLUMN IF NOT EXISTS region" in text, migration


def test_the_pack_budget_and_redaction_keep_the_field_region():
    fac = _field_ai_context()
    payload, _, _ = fac._apply_final_context_budget(
        {"field_profile": {"field_id": "f-1", "region": "unit-region"}, "active_season": None}
    )
    assert payload["field_profile"]["region"] == "unit-region"
    pack = fac.FieldAiContextPack(
        field_id="f-1",
        tenant_id="t-1",
        days=730,
        generated_at="2026-06-01T00:00:00Z",
        field_profile=payload["field_profile"],
        ai_context_summary_ar="-",
    ).model_dump(mode="json")
    owner_state = {"field_id": "f-1", "ai_context_pack": pack}
    assert runtime._trusted_region_for_generation(owner_state, "f-1", "t-1") == "unit-region"


def test_a_pack_for_another_field_or_tenant_gives_no_region():
    """A service caller's ``current_field_state`` for field B must not scope field A."""
    state = _owner_field_state("owner-region")
    assert runtime._trusted_region_for_generation(state, "f-1", "t-1") == "owner-region"
    assert runtime._trusted_region_for_generation(state, "f-2", "t-1") is None
    assert runtime._trusted_region_for_generation(state, "f-1", "t-2") is None
    assert runtime._trusted_region_for_generation(state, "f-1", None) is None


def test_rag_search_sends_no_region_filter_for_a_field_question():
    tree = ast.parse(Path(runtime.__file__).read_text(encoding="utf-8"))
    regions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [getattr(k, "value", None) for k in node.keys]
        if "region" in keys and "final_k" in keys:
            regions.append(ast.unparse(node.values[keys.index("region")]))
    assert regions == ["None if req.field_id else req.region"]

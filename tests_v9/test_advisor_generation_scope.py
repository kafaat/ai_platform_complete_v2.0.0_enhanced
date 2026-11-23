"""The advisor asks the approval gate with the question's crop and region (F6 follow-up).

``partition_generation_references`` admits an approved excerpt only when its applicability
matches the question's crop and region. The advisor called it with neither, so every excerpt
was held as ``question_crop_unknown`` even after an agronomist approved it. The scope follows
the rule retrieval already uses: a field question takes the crop from the owner's crop card,
never from the client; its region stays unknown because the owner context carries none, so a
client-sent region cannot admit an excerpt for that field. A general question has no owner
record, so the client's crop and region are its only scope.
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


def _partition(req, retrieval_crop):
    scope = runtime._generation_scope(req, retrieval_crop)
    return partition_generation_references([_excerpt()], approvals=_approvals(), as_of=ON, **scope)


def test_general_question_scope_admits_an_excerpt_approved_for_its_crop_and_region():
    req = SimpleNamespace(field_id=None, crop="unit-crop", region="unit-region")
    usable, held = _partition(req, retrieval_crop="unit-crop")
    assert [u["chunk_id"] for u in usable] == ["c-1"] and held == []


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
    assert [ast.unparse(k) for k in call.keywords] == ["**_generation_scope(req, retrieval_crop)"]

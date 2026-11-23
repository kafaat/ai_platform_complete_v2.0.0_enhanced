"""F6: an excerpt reaches the model context only through a matching approval record."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from datetime import date
from functools import partial
from pathlib import Path

import pytest

from shared.ai import reference_approvals as approvals_module
from shared.ai.reference_approvals import (
    MANIFEST_PATH,
    MANIFEST_SCHEMA,
    ApprovalManifestError,
    content_digest,
    index_approvals,
    load_manifest,
    validate_manifest,
)
from shared.ai.seed_claims import partition_generation_references

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TEXT = "placeholder excerpt used only by this test"
REVISION = "unit-rev-1"
TODAY = date(2026, 6, 1)
UNIT_CROP = "unit-crop"
UNIT_REGION = "unit-region"


def approval_record(text=TEXT, revision=REVISION, **overrides):
    """A structurally complete record for fixture text. It is never written to the manifest."""
    record = {
        "approval_id": f"unit-{content_digest(text)[:12]}-{revision}",
        "content_digest": content_digest(text),
        "source_revision": revision,
        "source": {
            "title": "unit fixture source",
            "publisher": "unit fixture publisher",
            "publication_date": "2025-01-15",
        },
        "reviewer": {"name": "Unit Reviewer", "identity": "unit-registry-0001"},
        "reviewed_on": "2026-01-10",
        "valid_until": "2026-12-31",
        "applicability": {
            "crops": [UNIT_CROP],
            "regions": [UNIT_REGION],
            "jurisdiction": "unit-jurisdiction",
        },
    }
    record.update(overrides)
    return record


def manifest_of(*records):
    return {"schema": MANIFEST_SCHEMA, "schema_version": 1, "approvals": list(records)}


def admit_fixture_excerpts(monkeypatch, *excerpts):
    """Stand in for an agronomist's approval of test fixtures and a matching question scope.

    The advisor imports the partition function at call time, so replacing it on its module
    reaches the runtime. The real check still runs; only its inputs are supplied here. The
    advisor passes the question's own scope (``_generation_scope``); this stand-in replaces it
    with the fixtures' scope, because these tests prove grounding, not scope derivation
    (that is ``test_advisor_generation_scope.py``).
    """
    from shared.ai import seed_claims

    index = index_approvals(
        manifest_of(*(approval_record(e["text"], e["source_revision"]) for e in excerpts))
    )

    def admit(items, **_question_scope):
        return partition_generation_references(
            items, approvals=index, crop=UNIT_CROP, region=UNIT_REGION, as_of=TODAY
        )

    monkeypatch.setattr(seed_claims, "partition_generation_references", admit)


def excerpt(**overrides):
    item = {
        "chunk_id": "upload:7:0",
        "document_id": "upload:7",
        "source_revision": REVISION,
        "text": TEXT,
    }
    item.update(overrides)
    return item


def partition(items, records=None, **scope):
    scope = {"crop": UNIT_CROP, "region": UNIT_REGION, "as_of": TODAY, **scope}
    index = index_approvals(manifest_of(*([approval_record()] if records is None else records)))
    return partition_generation_references(items, approvals=index, **scope)


def hold_reason(item=None, records=None, **scope):
    usable, held = partition([excerpt() if item is None else item], records, **scope)
    assert usable == []
    assert len(held) == 1 and "text" not in held[0]
    return held[0]["generation_hold_reason"]


def test_excerpt_nobody_reviewed_is_not_generation_eligible():
    """Audit witness: an excerpt outside the flagged seed list has no reviewer at all."""
    usable, held = partition_generation_references([excerpt()])
    assert usable == []
    assert [pointer["chunk_id"] for pointer in held] == ["upload:7:0"]
    assert all("text" not in pointer for pointer in held)


def test_shipped_manifest_is_valid_and_is_what_the_partition_reads(monkeypatch, tmp_path):
    assert validate_manifest(load_manifest(MANIFEST_PATH)) == []
    approvals_module.shipped_approvals.cache_clear()
    try:
        shipped = tmp_path / "reference_approvals.json"
        shipped.write_text(json.dumps(manifest_of(approval_record())), encoding="utf-8")
        monkeypatch.setattr(approvals_module, "MANIFEST_PATH", shipped)
        usable, held = partition_generation_references(
            [excerpt()], crop=UNIT_CROP, region=UNIT_REGION, as_of=TODAY
        )
        assert usable == [excerpt()] and held == []
    finally:
        approvals_module.shipped_approvals.cache_clear()


@pytest.mark.parametrize("content", ["{not json", json.dumps({"schema": "other"}), None])
def test_unusable_shipped_manifest_admits_nothing(monkeypatch, tmp_path, content):
    shipped = tmp_path / "reference_approvals.json"
    if content is not None:
        shipped.write_text(content, encoding="utf-8")
    approvals_module.shipped_approvals.cache_clear()
    try:
        monkeypatch.setattr(approvals_module, "MANIFEST_PATH", shipped)
        usable, held = partition_generation_references(
            [excerpt()], crop=UNIT_CROP, region=UNIT_REGION, as_of=TODAY
        )
        assert usable == []
        assert held[0]["generation_hold_reason"] == "approval_manifest_invalid"
    finally:
        approvals_module.shipped_approvals.cache_clear()


def test_matching_approval_admits_the_excerpt_unchanged():
    item = excerpt()
    usable, held = partition([item])
    assert usable == [item] and held == []
    # Scope names compare case- and width-insensitively, never by wildcard.
    assert partition([item], crop="  UNIT-Crop ", region="Unit-Region")[0] == [item]
    assert partition([item], jurisdiction="Unit-Jurisdiction")[0] == [item]


def test_validity_end_is_inclusive_and_review_date_is_a_start():
    assert partition([excerpt()], as_of=date(2026, 12, 31))[0] == [excerpt()]
    assert hold_reason(as_of=date(2027, 1, 1)) == "approval_expired"
    assert partition([excerpt()], as_of=date(2026, 1, 10))[0] == [excerpt()]
    assert hold_reason(as_of=date(2026, 1, 9)) == "approval_not_yet_effective"


@pytest.mark.parametrize(
    ("item", "scope", "reason"),
    [
        (excerpt(text=TEXT + "."), {}, "no_approval_record"),
        (excerpt(text=TEXT.upper()), {}, "no_approval_record"),
        (excerpt(source_revision="unit-rev-2"), {}, "no_approval_record"),
        (excerpt(source_revision=None), {}, "source_revision_missing"),
        (excerpt(source_revision="  "), {}, "source_revision_missing"),
        (excerpt(source_revision=7), {}, "source_revision_missing"),
        (excerpt(content_digest="0" * 64), {}, "content_digest_mismatch"),
        (excerpt(text=None), {}, "excerpt_has_no_text"),
        (excerpt(text="   "), {}, "excerpt_has_no_text"),
        (excerpt(), {"crop": "other-crop"}, "crop_not_applicable"),
        (excerpt(), {"crop": None}, "question_crop_unknown"),
        (excerpt(), {"crop": "*"}, "crop_not_applicable"),
        (excerpt(), {"region": "other-region"}, "region_not_applicable"),
        (excerpt(), {"region": None}, "question_region_unknown"),
        (excerpt(), {"region": ""}, "question_region_unknown"),
        (excerpt(), {"jurisdiction": "other-jurisdiction"}, "jurisdiction_not_applicable"),
    ],
)
def test_refusal_paths_hold_the_excerpt(item, scope, reason):
    assert hold_reason(item, **scope) == reason


def test_empty_manifest_admits_nothing():
    assert hold_reason(records=[]) == "no_approval_record"


def test_held_reference_stays_citable_without_its_text():
    item = excerpt(publisher="unit publisher", source_uri="https://example.invalid/doc", page=3)
    usable, held = partition([item, "not an object"], records=[])
    assert usable == []
    assert held[0] == {
        "chunk_id": "upload:7:0",
        "document_id": "upload:7",
        "publisher": "unit publisher",
        "source_uri": "https://example.invalid/doc",
        "source_revision": REVISION,
        "page": 3,
        "content_digest": content_digest(TEXT),
        "generation_hold_reason": "no_approval_record",
    }
    assert held[1] == {"chunk_id": None, "generation_hold_reason": "excerpt_is_not_an_object"}


@pytest.mark.parametrize(
    "item",
    [
        excerpt(chunk_id="seed:100"),
        excerpt(document_id="reference:unit source:153"),
        excerpt(claim_verification="not_verified_against_original"),
    ],
)
def test_flagged_seed_claim_stays_held_even_when_a_record_names_it(item):
    assert hold_reason(item) == "seed_claim_not_verified_against_original"


def _without(record, path):
    record = copy.deepcopy(record)
    target = record
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    return record


def _with(record, path, value):
    record = copy.deepcopy(record)
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return record


MANDATORY = [
    ("approval_id",),
    ("content_digest",),
    ("source_revision",),
    ("source",),
    ("source", "title"),
    ("source", "publisher"),
    ("source", "publication_date"),
    ("reviewer",),
    ("reviewer", "name"),
    ("reviewer", "identity"),
    ("reviewed_on",),
    ("valid_until",),
    ("applicability",),
    ("applicability", "crops"),
    ("applicability", "regions"),
    ("applicability", "jurisdiction"),
]


@pytest.mark.parametrize("path", MANDATORY, ids=".".join)
def test_validator_rejects_a_record_missing_a_mandatory_field(path):
    manifest = manifest_of(_without(approval_record(), path))
    assert validate_manifest(manifest)
    with pytest.raises(ApprovalManifestError):
        index_approvals(manifest)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("content_digest",), "ABC"),
        (("content_digest",), content_digest(TEXT).upper()),
        (("source_revision",), " "),
        (("source", "publication_date"), "2025"),
        (("source", "publication_date"), "2026-02-01"),
        (("source", "title"), ""),
        (("source", "unknown"), "x"),
        (("reviewer", "identity"), " "),
        (("reviewer", "name"), None),
        (("reviewer", "role"), "x"),
        (("reviewed_on",), "10/01/2026"),
        (("reviewed_on",), "2026-02-30"),
        (("valid_until",), None),
        (("valid_until",), "2026-01-09"),
        (("applicability", "crops"), []),
        (("applicability", "crops"), ["*"]),
        (("applicability", "crops"), "unit-crop"),
        (("applicability", "regions"), [""]),
        (("applicability", "regions"), ["unit-region", 3]),
        (("applicability", "jurisdiction"), "*"),
        (("applicability", "all_crops"), True),
        (("approved_by_default",), True),
    ],
)
def test_validator_rejects_malformed_values_wildcards_and_unknown_fields(path, value):
    assert validate_manifest(manifest_of(_with(approval_record(), path, value)))


def test_validator_rejects_a_bad_envelope_and_duplicate_records():
    record = approval_record()
    assert validate_manifest(manifest_of(record)) == []
    assert validate_manifest([record])
    assert validate_manifest({**manifest_of(record), "schema": "other"})
    assert validate_manifest({**manifest_of(record), "schema_version": 2})
    assert validate_manifest({**manifest_of(record), "schema_version": True})
    assert validate_manifest({**manifest_of(), "approvals": {}})
    assert validate_manifest({**manifest_of(record), "default": "approve"})
    assert validate_manifest(manifest_of(record, "not a record"))
    assert validate_manifest(manifest_of(record, {**record, "approval_id": "second"}))
    other = approval_record(text="another fixture")
    assert validate_manifest(manifest_of(record, {**other, "approval_id": record["approval_id"]}))
    assert validate_manifest(manifest_of(record, other)) == []


def test_one_invalid_record_voids_the_whole_manifest(tmp_path):
    bad = _without(approval_record(text="another fixture"), ("reviewer", "identity"))
    with pytest.raises(ApprovalManifestError):
        index_approvals(manifest_of(approval_record(), bad))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest_of(approval_record(), bad)), encoding="utf-8")
    assert approvals_module.main([str(path)]) == 1
    path.write_text(json.dumps(manifest_of(approval_record())), encoding="utf-8")
    assert approvals_module.main([str(path)]) == 0
    assert approvals_module.main([str(tmp_path / "absent.json")]) == 1


def _candidate_tool():
    path = ROOT / "services/qdrant-seed/list_review_candidates.py"
    spec = importlib.util.spec_from_file_location("list_review_candidates", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_tool_reports_review_status_per_excerpt():
    tool = _candidate_tool()
    index = index_approvals(manifest_of(approval_record()))
    excerpts = [
        excerpt(),
        excerpt(chunk_id="upload:7:1", text="unreviewed fixture"),
        excerpt(chunk_id="upload:7:2", source_revision="unit-rev-2"),
        excerpt(chunk_id="seed:100"),
        excerpt(chunk_id="upload:7:3", text=None),
    ]
    rows = tool.list_candidates(excerpts, index, today=TODAY)
    assert [(row["chunk_id"], row["review_status"]) for row in rows] == [
        ("upload:7:1", "awaiting_review"),
        ("upload:7:2", "awaiting_review"),
        ("seed:100", "flagged_not_verified_against_original"),
        ("upload:7:3", "no_text"),
    ]
    assert rows[0]["content_digest"] == content_digest("unreviewed fixture")
    assert rows[0]["source_revision"] == REVISION
    everything = tool.list_candidates(excerpts, index, today=TODAY, include_approved=True)
    assert everything[0]["review_status"] == "approved"
    expired = tool.list_candidates(excerpts[:1], index, today=date(2027, 1, 1))
    assert [row["review_status"] for row in expired] == ["approval_expired"]
    early = tool.list_candidates(excerpts[:1], index, today=date(2026, 1, 1))
    assert [row["review_status"] for row in early] == ["approval_not_yet_effective"]


def test_candidate_tool_reads_payload_exports_and_writes_no_approval(tmp_path, capsys):
    tool = _candidate_tool()
    before = MANIFEST_PATH.read_bytes()
    payloads = tmp_path / "payloads.json"
    payloads.write_text(
        json.dumps(
            [
                {
                    "page_content": TEXT,
                    "metadata": {"chunk_id": "upload:7:0", "source_revision": REVISION},
                }
            ]
        ),
        encoding="utf-8",
    )
    assert tool.main(["--payloads", str(payloads)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["excerpts_examined"] == 1
    assert report["review_status_counts"] == {"awaiting_review": 1}
    assert report["candidates"][0]["content_digest"] == content_digest(TEXT)
    assert MANIFEST_PATH.read_bytes() == before

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert tool.main(["--payloads", str(payloads), "--manifest", str(broken)]) == 2


def test_candidate_tool_lists_the_whole_seed_corpus_as_unapproved(monkeypatch, capsys):
    tool = _candidate_tool()
    import seed

    monkeypatch.setattr(seed, "SEED_TENANT_ID", "research-test")
    monkeypatch.setattr(seed, "_load_provenance_manifest", lambda: {})
    monkeypatch.setattr(seed, "_load_excluded_chunk_ids", lambda: frozenset({"seed:100"}))
    excerpts = tool.seed_excerpts()
    assert len(excerpts) == len(seed.KNOWLEDGE_BASE) - 1
    assert "seed:100" not in {row["chunk_id"] for row in excerpts}
    assert all(row["source_revision"] == seed.SEED_REVISION for row in excerpts)

    assert tool.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["approval_records"] == len(load_manifest(MANIFEST_PATH)["approvals"])
    by_id = {row["chunk_id"]: row for row in report["candidates"]}
    texts = {f"seed:{doc['id']}": doc["text"] for doc in seed.KNOWLEDGE_BASE}
    assert all(row["content_digest"] == content_digest(texts[cid]) for cid, row in by_id.items())
    usable, held = partition_generation_references(
        excerpts, crop=UNIT_CROP, region=UNIT_REGION, as_of=TODAY
    )
    assert usable == [] and len(held) == len(excerpts)

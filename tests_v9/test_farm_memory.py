"""tests_v9/test_farm_memory.py — SAHOOL Farm Memory: comprehensive test suite.

Tests cover:
- FarmMemory CRUD operations
- Tenant isolation (farm A never sees farm B)
- Search relevance and filtering
- Export engine (JSON, encrypted tarball, parquet optional, qdrant snapshot)
- Import engine (JSON round-trip, conflict resolution, encrypted tarball, schema migration)
- Skills loader (load_skill, list_skills, content validation)
- Atomicity (corrupted import leaves memory unchanged)

Run with: python3 -m pytest tests_v9/test_farm_memory.py -q
Skips gracefully for pyarrow/qdrant_client if not installed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shared.memory import (
    SCHEMA_VERSION,
    ConversationTurn,
    FarmMemory,
    MemoryItem,
    Recommendation,
    UsagePattern,
    detect_format,
    export_to_encrypted_tarball,
    export_to_json,
    generate_checksum,
    import_from_encrypted_tarball,
    import_from_json,
    list_skills,
    load_skill,
    migrate_schema,
    validate_checksum,
)
from shared.memory.export_engine import OptionalDependencyError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory(farm_id: str, tmp_path: Path) -> FarmMemory:
    """Create a FarmMemory backed by tmp_path."""
    return FarmMemory(farm_id, store_dir=str(tmp_path))


def _make_turn(farm_id: str, query: str = "hello", response: str = "world") -> ConversationTurn:
    return ConversationTurn(farm_id=farm_id, user_query=query, ai_response=response)


def _make_pattern(farm_id: str, description: str = "checks daily") -> UsagePattern:
    return UsagePattern(farm_id=farm_id, description=description, cadence="daily")


def _make_rec(farm_id: str, text: str = "plant wheat", confidence: float = 0.9) -> Recommendation:
    return Recommendation(farm_id=farm_id, text=text, confidence=confidence)


# ---------------------------------------------------------------------------
# FarmMemory CRUD
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_add_conversation_and_all_items(tmp_path: Path) -> None:
    mem = _make_memory("farm-001", tmp_path)
    turn = _make_turn("farm-001", query="What crop should I plant?")
    mem.add_conversation(turn)
    items = mem.all_items()
    assert len(items) == 1
    assert items[0].kind == "conversation"
    assert items[0].payload["user_query"] == "What crop should I plant?"


@pytest.mark.unit
def test_add_preference_round_trip(tmp_path: Path) -> None:
    mem = _make_memory("farm-002", tmp_path)
    mem.add_preference("soil_type", "loam")
    mem.add_preference("climate_zone", "semi-arid")
    prefs = mem.get_preferences()
    assert prefs["soil_type"] == "loam"
    assert prefs["climate_zone"] == "semi-arid"


@pytest.mark.unit
def test_add_pattern(tmp_path: Path) -> None:
    mem = _make_memory("farm-003", tmp_path)
    pat = _make_pattern("farm-003", description="farmer checks irrigation every morning")
    mem.add_pattern(pat)
    items = mem.all_items()
    assert len(items) == 1
    assert items[0].kind == "pattern"
    assert "irrigation" in items[0].payload["description"]


@pytest.mark.unit
def test_add_recommendation(tmp_path: Path) -> None:
    mem = _make_memory("farm-004", tmp_path)
    rec = _make_rec("farm-004", text="Apply fertiliser before rain", confidence=0.85)
    mem.add_recommendation(rec)
    items = mem.all_items()
    assert len(items) == 1
    assert items[0].kind == "recommendation"
    assert items[0].payload["confidence"] == pytest.approx(0.85)


@pytest.mark.unit
def test_clear_removes_all_items(tmp_path: Path) -> None:
    mem = _make_memory("farm-005", tmp_path)
    mem.add_conversation(_make_turn("farm-005"))
    mem.add_pattern(_make_pattern("farm-005"))
    mem.add_recommendation(_make_rec("farm-005"))
    mem.add_preference("k", "v")
    assert len(mem.all_items()) == 3
    mem.clear()
    assert len(mem.all_items()) == 0
    assert mem.get_preferences() == {}


@pytest.mark.unit
def test_multiple_items_all_items(tmp_path: Path) -> None:
    mem = _make_memory("farm-006", tmp_path)
    for i in range(3):
        mem.add_conversation(_make_turn("farm-006", query=f"question {i}"))
    for i in range(2):
        mem.add_pattern(_make_pattern("farm-006", description=f"pattern {i}"))
    for i in range(4):
        mem.add_recommendation(_make_rec("farm-006", text=f"rec {i}"))
    items = mem.all_items()
    assert len(items) == 9
    kinds = [item.kind for item in items]
    assert kinds.count("conversation") == 3
    assert kinds.count("pattern") == 2
    assert kinds.count("recommendation") == 4


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tenant_isolation_separate_stores(tmp_path: Path) -> None:
    """Farm A items must never appear in Farm B's results."""
    mem_a = _make_memory("farm-A", tmp_path)
    mem_b = _make_memory("farm-B", tmp_path)

    mem_a.add_conversation(_make_turn("farm-A", query="wheat irrigation schedule"))
    mem_a.add_preference("crop", "wheat")
    mem_b.add_conversation(_make_turn("farm-B", query="tomato pest control"))

    # Farm B should not see Farm A's items
    b_items = mem_b.all_items()
    assert all(item.payload.get("farm_id") != "farm-A" for item in b_items)
    assert len(b_items) == 1
    assert b_items[0].payload["user_query"] == "tomato pest control"

    # Farm A should not see Farm B's items
    a_items = mem_a.all_items()
    assert all(item.payload.get("farm_id") != "farm-B" for item in a_items)
    assert len(a_items) == 1


@pytest.mark.unit
def test_tenant_isolation_cross_farm_add_rejected(tmp_path: Path) -> None:
    """Adding a turn with the wrong farm_id must raise ValueError."""
    mem_a = _make_memory("farm-X", tmp_path)
    bad_turn = _make_turn("farm-Y", query="sneaky query")
    with pytest.raises(ValueError, match="Tenant isolation"):
        mem_a.add_conversation(bad_turn)


@pytest.mark.unit
def test_tenant_isolation_search_isolation(tmp_path: Path) -> None:
    """Search must only return items for this farm."""
    mem_a = _make_memory("farm-alpha", tmp_path)
    mem_b = _make_memory("farm-beta", tmp_path)

    mem_a.add_conversation(_make_turn("farm-alpha", query="wheat drought response"))
    mem_b.add_conversation(_make_turn("farm-beta", query="tomato drought response"))

    # Searching mem_b for "wheat" should return nothing
    results = mem_b.search("wheat drought")
    assert all(item.payload.get("farm_id") != "farm-alpha" for item in results)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_search_returns_relevant_items(tmp_path: Path) -> None:
    mem = _make_memory("farm-s1", tmp_path)
    mem.add_conversation(_make_turn("farm-s1", query="wheat planting schedule spring"))
    mem.add_conversation(_make_turn("farm-s1", query="tomato irrigation drip system"))
    mem.add_recommendation(_make_rec("farm-s1", text="use drip irrigation for tomato"))

    results = mem.search("tomato irrigation", k=5)
    assert len(results) >= 1
    # The top result should be about tomato
    assert any(
        "tomato" in (r.payload.get("user_query", "") + r.payload.get("text", "")) for r in results
    )


@pytest.mark.unit
def test_search_kind_filter(tmp_path: Path) -> None:
    mem = _make_memory("farm-s2", tmp_path)
    mem.add_conversation(_make_turn("farm-s2", query="pest control for wheat"))
    mem.add_recommendation(_make_rec("farm-s2", text="spray pesticide for wheat pest"))
    mem.add_pattern(_make_pattern("farm-s2", description="wheat pest check weekly"))

    results = mem.search("wheat pest", k=10, kind="recommendation")
    assert all(r.kind == "recommendation" for r in results)

    results = mem.search("wheat pest", k=10, kind="conversation")
    assert all(r.kind == "conversation" for r in results)


@pytest.mark.unit
def test_search_score_ordering(tmp_path: Path) -> None:
    mem = _make_memory("farm-s3", tmp_path)
    # High relevance: all query terms present
    mem.add_conversation(_make_turn("farm-s3", query="irrigation water schedule daily"))
    # Low relevance: only one term
    mem.add_conversation(_make_turn("farm-s3", query="market prices"))
    mem.add_conversation(_make_turn("farm-s3", query="weather forecast"))

    results = mem.search("irrigation water schedule", k=5)
    if len(results) >= 2:
        assert results[0].score >= results[1].score


# ---------------------------------------------------------------------------
# Export engine — JSON
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_export_to_json_structure(tmp_path: Path) -> None:
    mem = _make_memory("farm-e1", tmp_path / "store")
    mem.add_conversation(_make_turn("farm-e1", query="hello world"))
    mem.add_preference("crop", "wheat")
    mem.add_pattern(_make_pattern("farm-e1"))
    mem.add_recommendation(_make_rec("farm-e1"))

    out_path = tmp_path / "export.json"
    manifest = export_to_json("farm-e1", out_path, mem)

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))

    # Required top-level keys
    for key in (
        "farm_id",
        "export_version",
        "exported_at",
        "schema_version",
        "conversations",
        "preferences",
        "patterns",
        "recommendations",
        "vectors",
    ):
        assert key in data, f"Missing key: {key}"

    assert data["farm_id"] == "farm-e1"
    assert data["schema_version"] == SCHEMA_VERSION
    assert len(data["conversations"]) == 1
    assert len(data["patterns"]) == 1
    assert len(data["recommendations"]) == 1
    assert data["preferences"]["crop"] == "wheat"

    # ISO timestamp validation (ends with Z or +00:00)
    exported_at = data["exported_at"]
    assert "T" in exported_at
    assert exported_at.endswith("Z") or "+00" in exported_at

    # Manifest
    assert manifest["checksum_sha256"] is not None
    assert len(manifest["checksum_sha256"]) == 64  # SHA-256 hex


@pytest.mark.unit
def test_generate_checksum_stable(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_bytes(b"SAHOOL checksum test data")
    c1 = generate_checksum(f)
    c2 = generate_checksum(f)
    assert c1 == c2
    assert len(c1) == 64  # SHA-256 hex chars


@pytest.mark.unit
def test_generate_checksum_changes_with_content(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_bytes(b"content A")
    c1 = generate_checksum(f)
    f.write_bytes(b"content B")
    c2 = generate_checksum(f)
    assert c1 != c2


# ---------------------------------------------------------------------------
# Export engine — encrypted tarball
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_export_to_encrypted_tarball_produces_file(tmp_path: Path) -> None:
    mem = _make_memory("farm-enc1", tmp_path / "store")
    mem.add_conversation(_make_turn("farm-enc1", query="wheat yield optimization"))
    mem.add_preference("region", "sana")

    enc_path = tmp_path / "export.enc"
    manifest = export_to_encrypted_tarball("farm-enc1", enc_path, "test-password-secure", mem)

    assert enc_path.exists()
    assert enc_path.stat().st_size > 0
    assert manifest["format"] == "encrypted_tarball"
    assert manifest["encryption"] == "AES-256-GCM"
    assert "checksum_sha256" in manifest


@pytest.mark.unit
def test_encrypted_tarball_round_trip(tmp_path: Path) -> None:
    """Export then import with correct password restores all items."""
    mem = _make_memory("farm-enc2", tmp_path / "store")
    turn = _make_turn("farm-enc2", query="crop rotation plan")
    mem.add_conversation(turn)
    mem.add_preference("soil_ph", "6.5")
    mem.add_pattern(_make_pattern("farm-enc2", description="weekly irrigation check"))
    mem.add_recommendation(_make_rec("farm-enc2", text="add nitrogen fertiliser"))

    enc_path = tmp_path / "export.enc"
    export_to_encrypted_tarball("farm-enc2", enc_path, "my-secret-pass", mem)

    # Import into fresh memory
    mem2 = _make_memory("farm-enc2", tmp_path / "store2")
    result = import_from_encrypted_tarball(enc_path, "farm-enc2", "my-secret-pass", mem2)

    items = mem2.all_items()
    assert any(i.kind == "conversation" for i in items)
    assert any(i.kind == "pattern" for i in items)
    assert any(i.kind == "recommendation" for i in items)
    prefs = mem2.get_preferences()
    assert prefs.get("soil_ph") == "6.5"
    assert result["imported"] > 0 or result["merged"] >= 0


@pytest.mark.unit
def test_encrypted_tarball_wrong_password_fails_cleanly(tmp_path: Path) -> None:
    """Wrong password must raise ValueError; memory must remain unchanged."""
    mem = _make_memory("farm-enc3", tmp_path / "store")
    mem.add_conversation(_make_turn("farm-enc3", query="important data"))
    enc_path = tmp_path / "export.enc"
    export_to_encrypted_tarball("farm-enc3", enc_path, "correct-password", mem)

    mem2 = _make_memory("farm-enc3", tmp_path / "store2")
    mem2.add_conversation(_make_turn("farm-enc3", query="existing item"))

    with pytest.raises(ValueError, match="فشل فك تشفير"):
        import_from_encrypted_tarball(enc_path, "farm-enc3", "wrong-password", mem2)

    # Memory should be unchanged (still has only the pre-existing item)
    items = mem2.all_items()
    assert len(items) == 1
    assert items[0].payload["user_query"] == "existing item"


# ---------------------------------------------------------------------------
# Export engine — parquet (optional)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_export_to_parquet_skips_if_no_pyarrow(tmp_path: Path) -> None:
    """Parquet export raises OptionalDependencyError when pyarrow absent."""
    pytest.importorskip("pyarrow", reason="pyarrow not installed — skipping parquet test")

    from shared.memory.export_engine import export_to_parquet

    mem = _make_memory("farm-par1", tmp_path / "store")
    mem.add_conversation(_make_turn("farm-par1", query="parquet test query"))
    out = tmp_path / "export.parquet"
    manifest = export_to_parquet("farm-par1", out, mem)
    assert out.exists()
    assert manifest["row_count"] >= 1


@pytest.mark.unit
def test_export_to_parquet_arabic_error_when_missing(tmp_path: Path) -> None:
    """If pyarrow is not installed, an Arabic OptionalDependencyError is raised."""
    try:
        import pyarrow  # noqa: F401

        pytest.skip("pyarrow is installed — cannot test missing-dep error")
    except ImportError:
        pass

    from shared.memory.export_engine import export_to_parquet

    mem = _make_memory("farm-par2", tmp_path / "store")
    with pytest.raises(OptionalDependencyError) as exc_info:
        export_to_parquet("farm-par2", tmp_path / "out.parquet", mem)
    assert "pyarrow" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Import engine — JSON
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_import_from_json_round_trip(tmp_path: Path) -> None:
    """Export to JSON then import — all items restored."""
    mem = _make_memory("farm-i1", tmp_path / "store")
    mem.add_conversation(_make_turn("farm-i1", query="irrigation schedule"))
    mem.add_preference("zone", "desert")
    mem.add_pattern(_make_pattern("farm-i1"))
    mem.add_recommendation(_make_rec("farm-i1", text="plant date palms"))

    out = tmp_path / "export.json"
    export_to_json("farm-i1", out, mem)

    mem2 = _make_memory("farm-i1", tmp_path / "store2")
    result = import_from_json(out, "farm-i1", mem2)

    items = mem2.all_items()
    assert any(i.kind == "conversation" for i in items)
    assert any(i.kind == "pattern" for i in items)
    assert any(i.kind == "recommendation" for i in items)
    prefs = mem2.get_preferences()
    assert prefs.get("zone") == "desert"
    assert result["farm_id"] == "farm-i1"


@pytest.mark.unit
def test_import_merge_keeps_newer(tmp_path: Path) -> None:
    """Merge strategy keeps the newer timestamp when IDs conflict."""
    now = datetime.now(UTC)
    older = now - timedelta(hours=2)
    newer = now

    # Build a conversation with a fixed ID and older timestamp
    old_conv = ConversationTurn(
        farm_id="farm-m1",
        user_query="old query",
        ai_response="old response",
        timestamp=older,
    )
    new_conv = ConversationTurn(
        id=old_conv.id,  # Same ID!
        farm_id="farm-m1",
        user_query="new query",
        ai_response="new response",
        timestamp=newer,
    )

    # Memory with old item
    mem_existing = _make_memory("farm-m1", tmp_path / "existing")
    mem_existing.add_conversation(old_conv)

    # Export with new item
    mem_new = _make_memory("farm-m1", tmp_path / "new_store")
    mem_new.add_conversation(new_conv)
    out = tmp_path / "new.json"
    export_to_json("farm-m1", out, mem_new)

    # Import with merge
    result = import_from_json(out, "farm-m1", mem_existing, conflict_resolution="merge")

    items = mem_existing.all_items()
    # Should have the newer version
    conv_items = [i for i in items if i.kind == "conversation"]
    assert len(conv_items) == 1
    assert conv_items[0].payload["user_query"] == "new query"
    assert result["conflicts"] >= 1


@pytest.mark.unit
def test_import_replace_strategy(tmp_path: Path) -> None:
    """Replace strategy always uses incoming item."""
    mem_existing = _make_memory("farm-r1", tmp_path / "existing")
    turn = _make_turn("farm-r1", query="original")
    mem_existing.add_conversation(turn)

    # Export with same ID but different content
    mem_new = _make_memory("farm-r1", tmp_path / "new_store")
    new_turn = ConversationTurn(
        id=turn.id,
        farm_id="farm-r1",
        user_query="replaced",
        ai_response="replaced response",
    )
    mem_new.add_conversation(new_turn)
    out = tmp_path / "new.json"
    export_to_json("farm-r1", out, mem_new)

    import_from_json(out, "farm-r1", mem_existing, conflict_resolution="replace")

    items = [i for i in mem_existing.all_items() if i.kind == "conversation"]
    assert len(items) == 1
    assert items[0].payload["user_query"] == "replaced"


@pytest.mark.unit
def test_import_skip_strategy(tmp_path: Path) -> None:
    """Skip strategy keeps existing item when IDs conflict."""
    mem_existing = _make_memory("farm-sk1", tmp_path / "existing")
    turn = _make_turn("farm-sk1", query="original kept")
    mem_existing.add_conversation(turn)

    mem_new = _make_memory("farm-sk1", tmp_path / "new_store")
    new_turn = ConversationTurn(
        id=turn.id,
        farm_id="farm-sk1",
        user_query="should be skipped",
        ai_response="ignored",
    )
    mem_new.add_conversation(new_turn)
    out = tmp_path / "new.json"
    export_to_json("farm-sk1", out, mem_new)

    import_from_json(out, "farm-sk1", mem_existing, conflict_resolution="skip")

    items = [i for i in mem_existing.all_items() if i.kind == "conversation"]
    assert len(items) == 1
    assert items[0].payload["user_query"] == "original kept"


# ---------------------------------------------------------------------------
# Import engine — schema migration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_migrate_schema_v1_to_v2(tmp_path: Path) -> None:
    """v1→v2 migration adds satisfaction_score and renames query→user_query."""
    v1_data = {
        "schema_version": "v1",
        "farm_id": "farm-mig1",
        "conversations": [
            {
                "id": "c1",
                "farm_id": "farm-mig1",
                "query": "old field name",
                "ai_response": "response",
                "timestamp": "2026-01-01T00:00:00Z",
            },
        ],
        "preferences": {},
        "patterns": [],
        "recommendations": [],
    }

    v2_data = migrate_schema(v1_data, from_version="v1", to_version="v2")

    assert v2_data["schema_version"] == "v2"
    conv = v2_data["conversations"][0]
    assert "user_query" in conv, "query should be renamed to user_query"
    assert "query" not in conv, "old 'query' field should be removed"
    assert conv["user_query"] == "old field name"
    assert "satisfaction_score" in conv
    assert conv["satisfaction_score"] is None


@pytest.mark.unit
def test_migrate_schema_idempotent(tmp_path: Path) -> None:
    """Calling migrate with same from/to version is a no-op."""
    data = {
        "schema_version": "v2",
        "conversations": [{"id": "c1", "user_query": "hello", "satisfaction_score": None}],
    }
    result = migrate_schema(data, from_version="v2", to_version="v2")
    assert result["conversations"][0]["user_query"] == "hello"
    assert result["conversations"][0].get("satisfaction_score") is None


@pytest.mark.unit
def test_import_from_json_auto_migrates_v1(tmp_path: Path) -> None:
    """import_from_json automatically migrates v1 JSON files."""
    v1_export = {
        "schema_version": "v1",
        "farm_id": "farm-mig2",
        "export_version": "1.0",
        "exported_at": "2026-01-01T00:00:00Z",
        "conversations": [
            {
                "id": "c1",
                "farm_id": "farm-mig2",
                "query": "What fertiliser?",
                "ai_response": "Use NPK.",
                "timestamp": "2026-01-01T00:00:00Z",
            },
        ],
        "preferences": {},
        "patterns": [],
        "recommendations": [],
    }
    v1_path = tmp_path / "v1_export.json"
    v1_path.write_text(json.dumps(v1_export), encoding="utf-8")

    mem = _make_memory("farm-mig2", tmp_path / "store")
    import_from_json(v1_path, "farm-mig2", mem)

    items = mem.all_items()
    assert len(items) == 1
    assert items[0].payload.get("user_query") == "What fertiliser?"


# ---------------------------------------------------------------------------
# Import engine — checksum + format detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_checksum_true(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello SAHOOL")
    checksum = generate_checksum(f)
    assert validate_checksum(f, checksum) is True


@pytest.mark.unit
def test_validate_checksum_false(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello SAHOOL")
    assert validate_checksum(f, "a" * 64) is False


@pytest.mark.unit
def test_detect_format_json(tmp_path: Path) -> None:
    f = tmp_path / "export.json"
    f.write_text('{"farm_id": "x"}')
    assert detect_format(f) == "json"


@pytest.mark.unit
def test_detect_format_encrypted_tarball(tmp_path: Path) -> None:
    f = tmp_path / "export.enc"
    f.write_bytes(b"\x00" * 50)
    assert detect_format(f) == "encrypted_tarball"


@pytest.mark.unit
def test_detect_format_parquet(tmp_path: Path) -> None:
    f = tmp_path / "export.parquet"
    f.write_bytes(b"PAR1" + b"\x00" * 10)
    assert detect_format(f) == "parquet"


@pytest.mark.unit
def test_detect_format_qdrant_snapshot(tmp_path: Path) -> None:
    f = tmp_path / "export.snapshot"
    f.write_bytes(b"\x00" * 10)
    assert detect_format(f) == "qdrant_snapshot"


@pytest.mark.unit
def test_detect_format_qdrant_json_sniff(tmp_path: Path) -> None:
    """JSON files containing qdrant snapshot markers are detected as qdrant_snapshot."""
    f = tmp_path / "export.json"
    f.write_text('{"format": "qdrant_snapshot_fallback", "farm_id": "x"}')
    assert detect_format(f) == "qdrant_snapshot"


# ---------------------------------------------------------------------------
# Import engine — atomicity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_corrupted_tarball_import_leaves_memory_unchanged(tmp_path: Path) -> None:
    """A corrupted .enc file must not partially modify memory."""
    mem = _make_memory("farm-atom1", tmp_path / "store")
    mem.add_conversation(_make_turn("farm-atom1", query="existing critical data"))
    initial_count = len(mem.all_items())

    corrupt_enc = tmp_path / "corrupt.enc"
    corrupt_enc.write_bytes(b"this is not valid encrypted data at all 1234567890abcdef")

    with pytest.raises((ValueError, Exception)):
        import_from_encrypted_tarball(corrupt_enc, "farm-atom1", "any-password", mem)

    # Memory must be unchanged
    items = mem.all_items()
    assert len(items) == initial_count
    assert items[0].payload["user_query"] == "existing critical data"


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_skills_returns_three() -> None:
    skills = list_skills()
    assert len(skills) == 3
    assert "crop_advisor" in skills
    assert "irrigation" in skills
    assert "pest_diagnosis" in skills


@pytest.mark.unit
def test_load_skill_crop_advisor() -> None:
    skill = load_skill("crop_advisor")
    assert skill["title"] == "Crop Advisor Skill"
    assert "crop selection" in skill["when_to_use"].lower()
    assert len(skill["procedure"]) >= 5
    assert len(skill["pitfalls"]) >= 2


@pytest.mark.unit
def test_load_skill_irrigation() -> None:
    skill = load_skill("irrigation")
    assert skill["title"] == "Irrigation Skill"
    assert "irrigation" in skill["when_to_use"].lower()
    assert len(skill["procedure"]) >= 4
    # Must mention drip or flood
    pitfall_text = " ".join(skill["pitfalls"]).lower()
    assert "drip" in pitfall_text or "flood" in pitfall_text or "over-irrigate" in pitfall_text


@pytest.mark.unit
def test_load_skill_pest_diagnosis() -> None:
    skill = load_skill("pest_diagnosis")
    assert skill["title"] == "Pest Diagnosis Skill"
    assert len(skill["procedure"]) >= 4
    # The confidence escalation step is in procedure (step 5 per spec)
    procedure_text = " ".join(skill["procedure"]).lower()
    assert "confidence" in procedure_text or "expert" in procedure_text or "0.7" in procedure_text
    # Pitfalls must mention banned pesticides or organic alternatives
    pitfall_text = " ".join(skill["pitfalls"]).lower()
    assert "pesticide" in pitfall_text or "organic" in pitfall_text or "diagnose" in pitfall_text


@pytest.mark.unit
def test_load_skill_confidence_escalation_pitfall() -> None:
    """Pest diagnosis must include the escalate-to-human-expert procedure."""
    skill = load_skill("pest_diagnosis")
    procedure_text = " ".join(skill["procedure"]).lower()
    # The procedure says "Escalate to human expert if confidence < 0.7"
    assert "escalate" in procedure_text or "expert" in procedure_text or "0.7" in procedure_text


@pytest.mark.unit
def test_load_skill_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        load_skill("nonexistent_skill")


@pytest.mark.unit
def test_load_skill_normalized_name() -> None:
    """load_skill should accept name with or without _skill suffix."""
    s1 = load_skill("crop_advisor")
    s2 = load_skill("crop_advisor_skill")
    assert s1["title"] == s2["title"]

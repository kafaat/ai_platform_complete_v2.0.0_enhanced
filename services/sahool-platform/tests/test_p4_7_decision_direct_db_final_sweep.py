"""INTERIM direct-DB write sweep for decision loop tables (rescoped from the P4.7 sweep).

The original P4.7 sweep banned every direct loop-table ``INSERT``/``DELETE`` outside the
decision-service facade.  Under the chosen temporary bridge that ban is intentionally wrong:
sahool-platform is the temporary Source of Record, so a small, explicit allowlist of write
paths performs the AUTHORITATIVE loop-table write locally and then best-effort mirrors to
decision-service.  This guard keeps the protection honest by:

  1. still failing if ANY *unexpected* module gains a direct loop-table write, and
  2. asserting each allowlisted authoritative writer ALSO wires the decision-service mirror.

decision-service is documented (here and in the boundary contract) as NOT yet the SoR.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP_TABLES = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
)

# Non-DB-owning files that may legitimately name loop resources.
ALLOW_FILES = {
    "api/decision_service_client.py",  # transport facade may name service resources
    "api/decision_lineage.py",  # pure lineage naming; no DB ownership
    "api/learning_summary.py",  # pure summarizer model names; no DB ownership
}

# INTERIM authoritative writers: the temporary Source of Record for the loop tables.
# Each of these performs the local authoritative INSERT *and* mirrors to decision-service.
INTERIM_AUTHORITATIVE_WRITERS = {
    "api/routers/decision_record.py",
    "api/routers/decision_dispatch.py",
    "api/routers/recommendations.py",
    "api/phase_runtime_store.py",
    "api/routers/weather.py",
}

_MIRROR_TOKENS = (
    "_mirror_to_decision_service",
    "_mirror_decision_to_service",
    "_mirror_outcome_to_service",
    "_mirror_dispatch_to_service",
    "_mirror_recommendation_outcome_to_service",
    "_mirror_learning_update_to_service",
)


def test_only_the_interim_authoritative_writers_write_loop_tables_directly():
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel.startswith("tests/") or rel in ALLOW_FILES or rel in INTERIM_AUTHORITATIVE_WRITERS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for table in LOOP_TABLES:
            for verb in ("INSERT INTO", "DELETE FROM"):
                if f"{verb} {table}" in text:
                    offenders.append(f"{rel}: {verb} {table}")
    assert not offenders, (
        "Unexpected direct loop-table writes appeared outside the interim authoritative "
        "writer allowlist:\n" + "\n".join(offenders[:50])
    )


def test_each_interim_authoritative_writer_also_mirrors_to_decision_service():
    """No silent data divergence: every authoritative writer best-effort mirrors the write."""
    missing = []
    for rel in INTERIM_AUTHORITATIVE_WRITERS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        writes_loop = any(f"INSERT INTO {t}" in text for t in LOOP_TABLES)
        mirrors = any(tok in text for tok in _MIRROR_TOKENS)
        if not (writes_loop and mirrors):
            missing.append({"file": rel, "writes_loop": writes_loop, "mirrors": mirrors})
    assert not missing, "Interim authoritative writers must write locally AND mirror: " + repr(
        missing
    )


def test_decision_client_is_the_platform_boundary_for_the_mirror():
    text = (ROOT / "api/decision_service_client.py").read_text(encoding="utf-8")
    for name in (
        "record_decision",
        "record_dispatch_decision",
        "record_outcome",
        "record_recommendation_outcome",
        "record_learning_update",
        "get_learning_summary",
        "get_decision_lineage",
        "list_decisions",
        "get_field_lineage",
        "get_reconciled_outcomes",
    ):
        assert f"async def {name}" in text


def test_weather_and_learning_paths_write_authoritatively_then_mirror():
    weather = (ROOT / "api/routers/weather.py").read_text(encoding="utf-8")
    assert "INSERT INTO decision_record" in weather
    assert "_mirror_decision_to_service" in weather

    runtime = (ROOT / "api/phase_runtime_store.py").read_text(encoding="utf-8")
    assert "INSERT INTO online_learning_updates" in runtime
    assert "resolve_learning_source(update)" in runtime
    assert "record_learning_update as _mirror_learning_update_to_service" in runtime

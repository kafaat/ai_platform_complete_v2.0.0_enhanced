from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP_TABLES = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
)
ALLOW_FILES = {
    "api/decision_service_client.py",  # transport facade may name service resources
    "api/decision_lineage.py",  # pure lineage naming; no DB ownership
    "api/learning_summary.py",  # pure summarizer model names; no DB ownership
}


def test_platform_no_new_direct_loop_table_writes_outside_known_legacy_or_facade():
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel.startswith("tests/") or rel in ALLOW_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for table in LOOP_TABLES:
            for verb in ("INSERT INTO", "DELETE FROM"):
                if f"{verb} {table}" in text:
                    # P4.7 converted primary loop ownership writes.  Dispatch status UPDATEs
                    # remain legacy execution-state exceptions until the worker split.
                    offenders.append(f"{rel}: {verb} {table}")
    assert not offenders, (
        "Direct loop-table writes remain outside decision-service facade:\n"
        + "\n".join(offenders[:50])
    )


def test_decision_client_is_the_platform_boundary_for_loop_reads_and_writes():
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


def test_weather_derived_decision_and_source_persist_delegate_to_facade():
    weather = (ROOT / "api/routers/weather.py").read_text(encoding="utf-8")
    assert "INSERT INTO decision_record" not in weather
    assert "record_decision as _record_decision_via_service" in weather

    runtime = (ROOT / "api/phase_runtime_store.py").read_text(encoding="utf-8")
    assert "INSERT INTO online_learning_updates" not in runtime
    assert "resolve_learning_source(update)" in runtime
    assert "record_learning_update as _record_learning_update_via_service" in runtime

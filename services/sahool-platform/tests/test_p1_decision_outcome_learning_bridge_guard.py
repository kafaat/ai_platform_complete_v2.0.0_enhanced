from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
CONTRACT = ROOT / "docs" / "architecture" / "DECISION_OUTCOME_LEARNING_BRIDGE_CONTRACT.md"
ALLOWLIST = ROOT / "docs" / "architecture" / "decision_outcome_learning_bridge_allowlist.json"
MAP_PATH = ROOT / "docs" / "architecture" / "platform_extraction_map.json"
DB_OWNERSHIP = ROOT / "docs" / "architecture" / "db_ownership.yml"
PHASE_RUNTIME_STORE = PLATFORM / "api" / "phase_runtime_store.py"


def _load_simple_yaml_tables(path: Path) -> dict[str, dict[str, object]]:
    tables: dict[str, dict[str, object]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#") or line.strip() == "tables:":
            continue
        table_match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if table_match:
            current = table_match.group(1)
            tables[current] = {}
            continue
        prop_match = re.match(r"^    ([a-z_]+):\s*(.*)$", line)
        if current and prop_match:
            key, value = prop_match.group(1), prop_match.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                tables[current][key] = [part.strip() for part in inner.split(",") if part.strip()]
            else:
                tables[current][key] = value.strip('"')
    return tables


def test_decision_outcome_learning_bridge_contract_exists_and_names_rules():
    assert CONTRACT.exists(), "P1 decision/outcome/learning bridge contract is required."
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "online_learning_updates",
        "traceability_status",
        "recommendation_feedback",
        "core.outcome_reconciler",
        "core.loop_referential_integrity",
        "learning update is never silently trusted",
    ]
    missing = [marker for marker in required if marker not in text]
    assert not missing, "Bridge contract is missing required loop-closure rules: " + repr(missing)


def test_core_bridge_artifacts_and_migrations_are_present():
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    missing = []
    for rel in allow["required_core_bridge_files"] + allow["required_migrations"]:
        if not (ROOT / rel if rel.startswith("migrations/") else PLATFORM / rel).exists():
            missing.append(rel)
    assert not missing, "Decision/outcome/learning bridge artifacts are missing: " + repr(missing)


def test_online_learning_update_writer_resolves_source_lineage_before_delegating():
    """P4.7: online_learning_updates ownership moved to decision-service.

    The invariant is preserved, not dropped: the platform still resolves explicit source
    lineage *before* the write leaves it (``resolve_learning_source``), then delegates the
    write to the single owner (decision-service), which recomputes ``traceability_status``.
    A learning update is therefore still never silently trusted, and there is no direct
    loop-table INSERT left on this path.
    """
    text = PHASE_RUNTIME_STORE.read_text(encoding="utf-8", errors="ignore")
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    # Lineage input columns are still forwarded; traceability_status is now computed by the
    # owner service (decision-service._traceability), so it is not asserted on the writer.
    lineage_inputs = [c for c in allow["learning_source_columns"] if c != "traceability_status"]
    required = [
        "resolve_learning_source(update)",
        "record_learning_update as _record_learning_update_via_service",
    ] + lineage_inputs
    missing = [marker for marker in required if marker not in text]
    assert not missing, (
        "learning update writer must resolve source lineage then delegate to the owner: "
        + repr(missing)
    )
    assert "INSERT INTO online_learning_updates" not in text, (
        "P4.7: platform must not directly own the online_learning_updates write."
    )


def test_learning_lineage_migration_adds_source_columns_and_constraints():
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    migration = (ROOT / "migrations" / "v151_learning_source_lineage.sql").read_text(
        encoding="utf-8", errors="ignore"
    )
    required = allow["learning_source_columns"] + [
        "chk_oluj_source_type",
        "chk_oluj_traceability_status",
        "idx_oluj_untraceable",
        "recommendation_outcome",
        "outcome_record",
        "execution_feedback",
        "human_feedback",
    ]
    missing = [marker for marker in required if marker not in migration]
    assert not missing, "v151 learning lineage migration is incomplete: " + repr(missing)


def test_recommendation_feedback_is_deprecated_and_has_no_runtime_writer():
    migration = (ROOT / "migrations" / "v152_deprecate_recommendation_feedback.sql").read_text(
        encoding="utf-8", errors="ignore"
    )
    assert "DEPRECATED" in migration and "recommendation_outcomes" in migration

    offenders = []
    insert_re = re.compile(r"INSERT\s+INTO\s+recommendation_feedback\b", re.I)
    for base in [ROOT / "services"]:
        for path in base.rglob("*.py"):
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if insert_re.search(text):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, (
        "Deprecated recommendation_feedback must not gain a runtime writer: " + repr(offenders[:20])
    )


def test_loop_tables_are_registered_with_single_owner():
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    tables = _load_simple_yaml_tables(DB_OWNERSHIP)
    missing = [name for name in allow["loop_tables"] if name not in tables]
    assert not missing, "Loop tables missing from db_ownership.yml: " + repr(missing)
    bad = []
    for name in allow["loop_tables"]:
        meta = tables[name]
        if not meta.get("owner") or meta.get("writers") != [meta.get("owner")]:
            bad.append({"table": name, "meta": meta})
    assert not bad, "Loop tables must have exactly one registered writer/owner: " + repr(bad)


def test_decisionish_routes_have_explicit_allowed_target_owner():
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    allowed = set(allow["allowed_target_owners"])
    keywords = [k.lower() for k in allow["decision_route_keywords"]]
    extraction_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    violations = []
    for route in extraction_map["routes"]:
        haystack = " ".join([route["file"], route["function"], route["path"]]).lower()
        if any(k in haystack for k in keywords) and route.get("target_owner") not in allowed:
            violations.append(
                {"route": route["route_key"], "target_owner": route.get("target_owner")}
            )
    assert not violations, (
        "Decision/outcome/learning routes must have an explicit approved target owner: "
        + repr(violations[:30])
    )


def test_outcome_reconciler_is_wired_into_learning_summary_read_path():
    """The bridge must not remain pure-only; reconciliation logic must stay live.

    P4.6 read-side facade: the learning-summary *route* no longer reads loop tables itself —
    it delegates to decision-service (the owner).  The pure reconciliation logic still lives
    in ``api/learning_summary.py`` (asserted below) and is still consumed on a live read path
    by the field-season projection (see the dedicated test), so the reconciler is not orphaned.
    """
    summary_core = (PLATFORM / "api" / "learning_summary.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    summary_router = (PLATFORM / "api" / "routers" / "learning_summary.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    required_core = [
        "from core.outcome_reconciler import reconcile_outcomes",
        "summarize_learning_with_reconciled_outcomes",
        "outcome_reconciliation",
        "by_source",
        "linked_group_count",
    ]
    missing_core = [marker for marker in required_core if marker not in summary_core]
    assert not missing_core, (
        "learning summary core must expose reconciled outcome metadata: " + repr(missing_core)
    )

    # Route now delegates read semantics to the owning service (no direct loop-table reads).
    required_router = ["decision_service_client", "get_learning_summary"]
    missing_router = [marker for marker in required_router if marker not in summary_router]
    assert not missing_router, (
        "learning summary route must delegate reads to decision-service: " + repr(missing_router)
    )
    for forbidden in (
        "FROM recommendation_outcomes",
        "FROM dispatch_decisions",
        "tenant_connection",
    ):
        assert forbidden not in summary_router, (
            "P4.6: learning summary route must not read loop tables directly: " + forbidden
        )


def test_outcome_reconciler_is_wired_into_field_season_state_projection():
    """Seasonal operational truth must expose reconciled outcomes, not raw-only outcomes."""
    projection = (PLATFORM / "api" / "field_season_projection.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    seasons_router = (PLATFORM / "api" / "routers" / "seasons.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    required_projection = [
        "from core.outcome_reconciler import reconcile_outcomes",
        "_summarize_reconciled_outcomes_for_season",
        "outcome_reconciliation",
        "linked_group_count",
        "sample_count",
    ]
    missing_projection = [marker for marker in required_projection if marker not in projection]
    assert not missing_projection, (
        "field_season_projection must expose reconciled outcome metadata: "
        + repr(missing_projection)
    )

    required_router = [
        "FROM outcome_record",
        "FROM recommendation_outcomes",
        "FROM dispatch_decisions",
        "outcome_records=outcome_records",
        "recommendation_outcomes=recommendation_outcomes",
        "dispatch_links=dispatch_links",
    ]
    missing_router = [marker for marker in required_router if marker not in seasons_router]
    assert not missing_router, (
        "field season state route must read reconciled outcome inputs best-effort: "
        + repr(missing_router)
    )

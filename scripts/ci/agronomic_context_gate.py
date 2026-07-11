"""AC-1 gate: the agronomic-context contract layer must stay canonical and fail-closed.

Guards the master-plan Phase A invariants: the three immutable contract tables exist with
append-only enforcement, decision_record carries mandatory-binding columns, the composer enforces
point-in-time (future leakage is a TYPED rejection, never silent), and the record path validates
supplied lineage. No source value may be synthesized inside the composer.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
mig = (ROOT / "services/decision-service/migrations/018_ac1_agronomic_context.sql").read_text()
persist = (ROOT / "services/decision-service/persistence.py").read_text()
main = (ROOT / "services/decision-service/main.py").read_text()
contracts = (ROOT / "services/decision-service/agronomic_context/contracts.py").read_text()
pit = (ROOT / "services/decision-service/agronomic_context/point_in_time.py").read_text()

for token in (
    "decision_agronomic_context_snapshots",
    "decision_field_historical_context_snapshots",
    "decision_feature_manifests",
    "decision_feature_manifest_entries",
    "context_contract_version",
    "legacy_unbound",
    "observed_at <= available_at",
):
    assert token in mig, f"migration 018 missing: {token}"

for token in (
    "future_leakage",
    "available_at > cutoff",
    "missing_context_groups",
):
    assert token in pit, f"point_in_time missing: {token}"

for token in ("CONTEXT_GROUPS", "QUALITY_STATES", "class ContextComposeIn"):
    assert token in contracts, f"contracts missing: {token}"

for token in (
    "async def compose_agronomic_context",
    "point_in_time_policy",
    "_validate_decision_context",
    "partial_context_binding",
    '"ac-1" if has_context else "legacy_unbound"',
):
    assert token in persist, f"persistence missing: {token}"

for token in (
    '"/v1/context-snapshots"',
    "DECISION_REQUIRE_AGRONOMIC_CONTEXT",
    "agronomic_context_snapshot_id",
):
    assert token in main, f"main.py missing: {token}"

# the composer must never synthesize source values.
seg = persist[persist.index("async def compose_agronomic_context") :]
seg = seg[: seg.index("async def get_context_snapshot")]
for forbidden in ("random.", "uniform(", "synthetic", "np.random"):
    assert forbidden not in seg, f"composer must not synthesize values: {forbidden}"
print("AC-1 agronomic context gate: PASS")

"""WX-12.3 scheduler gate: monitoring/reconcile scheduling must be durable and actually wired.

The forensic audit found the supervisor handled monitoring_window/active_state_reconcile but the
feed never emitted them (dormant code). This gate fails if that regresses: the schedule config
table + reconcile evidence table must exist, the feed must emit both kinds, the endpoints must be
mounted, and the supervisor must consume reconcile work (not skip it).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
mig = (ROOT / "services/decision-service/migrations/017_wx12_runtime_schedules.sql").read_text(
    encoding="utf-8"
)
persist = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
main = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
service = (ROOT / "services/model-registry-adapter/service.py").read_text(encoding="utf-8")
runtime = (ROOT / "services/model-registry-adapter/runtime.py").read_text(encoding="utf-8")

for token in (
    "decision_model_runtime_schedules",
    "decision_model_reconcile_evidence",
    "'monitoring_window','active_state_reconcile'",
):
    assert token in mig, f"migration 017 missing: {token}"
# the claim CHECK must accept the scheduled work types (multi-replica leasing covers them too)
assert "'retraining_dispatch','monitoring_window','active_state_reconcile'" in mig

for token in (
    "s.kind='monitoring_window'",
    "s.kind='active_state_reconcile'",
    "MODEL_RUNTIME_SCHEDULE_CREATED",
    "MODEL_RECONCILE_EVIDENCE_RECORDED",
):
    assert token in persist, f"persistence missing: {token}"

for token in ('"/v1/learning/runtime-schedules"', '"/v1/learning/reconcile-evidence"'):
    assert token in main, f"main.py missing endpoint: {token}"

assert "runtime.reconcile_and_report(tenant, payload)" in service, (
    "supervisor must consume active_state_reconcile"
)
assert "def reconcile_and_report" in runtime and '"idempotency_key": f"reconcile:' in runtime

# the scheduled work stays evidence-only: no training/actuation from the scheduler path.
seg = persist[persist.index("s.kind='monitoring_window'") :]
for forbidden in ("model.fit(", "optimizer.step(", "mqtt.publish(", "actuator"):
    assert forbidden not in seg, forbidden
print("WX-12.3 runtime scheduler gate: PASS")

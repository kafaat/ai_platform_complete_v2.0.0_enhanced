from pathlib import Path

req = {
    "migrations/v164_soil_p4_closed_loop.sql": [
        "soil_execution_records",
        "soil_learning_attributions",
        "FORCE ROW LEVEL SECURITY",
    ],
    "services/soil-service/p4_governance.py": [
        "POLICIES",
        "max_evidence_age_days",
        "block_on_conflict",
        "build_learning",
    ],
    "services/soil-service/routers/p4_workflow.py": [
        "/soil/actions/{action_type}/evaluate",
        "/soil/executions",
        "/soil/closed-loop",
    ],
    "shared/contracts/soil/p4.py": [
        "SoilExecutionRecord",
        "SoilVerificationRecord",
        "SoilOutcomeRecord",
        "SoilLearningAttribution",
    ],
}
for f, toks in req.items():
    s = Path(f).read_text()
    for x in toks:
        assert x in s, (f, x)
# Repository ratchet: direct soil primitives are forbidden in newly governed decision entrypoints.
for f in ["services/decision-service/main.py"]:
    s = Path(f).read_text()
    assert "DECISION_REQUIRE_SOIL_PROFILE" in s
print("soil_p4_closed_loop_guard_ok")

#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
main=(root/'services/decision-service/main.py').read_text()
persist=(root/'services/decision-service/persistence.py').read_text()
mig=(root/'services/decision-service/migrations/009_model_evaluation_run.sql').read_text()
assert '/v1/learning/evaluation-runs' in main
assert 'decision_model_evaluation_runs' in persist and 'MODEL_EVALUATION_RUN_CREATED' in persist
for forbidden in ('model.fit(', 'partial_fit(', 'optimizer.step(', 'promote_model', 'active_model_id', 'mqtt.publish(', 'actuator'):
    assert forbidden not in main[main.index('class ModelEvaluationRunIn'):], forbidden
    assert forbidden not in persist[persist.index('def _model_evaluation_hash'):], forbidden
assert 'append-only' in mig and "evaluation_state = 'evaluated'" in mig
print('WX-11.2 model evaluation boundary: PASS')

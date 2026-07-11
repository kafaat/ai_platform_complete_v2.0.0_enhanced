from pathlib import Path
root=Path(__file__).resolve().parents[2]
main=(root/'services/decision-service/main.py').read_text()
persistence=(root/'services/decision-service/persistence.py').read_text()
migration=(root/'services/decision-service/migrations/013_registry_adapter_receipt_rollback.sql').read_text()
router=(root/'services/sahool-platform/api/routers/decision_review.py').read_text()
for needle in [
 '/v1/learning/activation-commands/{activation_command_id}/claim',
 '/v1/learning/activation-commands/{activation_command_id}/receipt',
 '/v1/learning/activation-receipts/{activation_receipt_id}/rollback-command']:
    assert needle in main
    assert '/api'+needle in router
for table in ['decision_model_registry_activation_claims','decision_model_registry_activation_receipts','decision_model_registry_rollback_commands']:
    assert table in migration and table in persistence
for forbidden in ['model.fit(', 'optimizer.step(', 'mqtt.publish(', 'registry_alias =']:
    assert forbidden not in persistence.lower(), forbidden
assert 'MODEL_REGISTRY_ACTIVATION_COMMAND_CLAIMED' in persistence
assert 'MODEL_REGISTRY_ACTIVATION_RECEIPT_RECORDED' in persistence
assert 'MODEL_REGISTRY_ROLLBACK_COMMAND_CREATED' in persistence
print('WX-11.6 registry activation boundary: PASS')

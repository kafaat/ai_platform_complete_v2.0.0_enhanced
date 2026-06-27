from shared.runtime_worker_contracts import (
    build_actuator_worker_action,
    build_model_promotion_action,
    build_model_rollback_action,
    build_outbox_action,
    build_plugin_worker_action,
)


def test_outbox_fails_closed_without_nats_url():
    action = build_outbox_action(nats_url=None, event_type="field_created", attempts=0, max_attempts=5)
    assert action["status"] == "failed"
    assert action["reason"] == "nats_url_missing"
    assert "NATS_URL" in action["required_config"]


def test_plugin_worker_never_completes_without_executor_backend():
    action = build_plugin_worker_action(decision="allow", plugin_enabled=True, executor_url=None)
    assert action["status"] == "blocked"
    assert action["reason"] == "plugin_executor_url_missing"
    assert action["action"] != "completed"


def test_plugin_worker_queues_external_executor_when_configured():
    action = build_plugin_worker_action(decision="allow", plugin_enabled=True, executor_url="http://plugin-runner:8080")
    assert action["action"] == "enqueue_external_executor"
    assert action["status"] == "queued"
    assert action["external_call_required"] is True


def test_model_promotion_requires_artifact_metadata_and_serving_backend():
    missing_artifact = build_model_promotion_action(
        decision="promote",
        target_model_id="m1",
        artifact_uri=None,
        artifact_hash=None,
        serving_enabled=True,
        serving_backend_url="http://serving",
    )
    assert missing_artifact["status"] == "blocked"
    assert missing_artifact["reason"] == "artifact_metadata_missing"

    missing_backend = build_model_promotion_action(
        decision="promote",
        target_model_id="m1",
        artifact_uri="minio://bucket/model",
        artifact_hash="abc",
        serving_enabled=True,
        serving_backend_url=None,
    )
    assert missing_backend["reason"] == "model_serving_backend_url_missing"


def test_model_rollback_queues_only_with_serving_backend():
    action = build_model_rollback_action(rollback_enabled=True, serving_backend_url="http://serving", to_model_id="champion")
    assert action["action"] == "request_serving_rollback"
    assert action["status"] == "queued"


def test_actuator_requires_real_adapter_and_never_marks_physical_effect_before_ack():
    blocked = build_actuator_worker_action(physical_enabled=True, protocol="modbus_tcp", target_id="pump-1", adapter_config={})
    assert blocked["status"] == "adapter_required"
    assert blocked["physical_effect"] is False

    requested = build_actuator_worker_action(
        physical_enabled=True,
        protocol="modbus_tcp",
        target_id="pump-1",
        adapter_config={"modbus_tcp": {"enabled": True, "mode": "real", "endpoint": "tcp://10.0.0.10:502"}},
    )
    assert requested["status"] == "waiting_ack"
    assert requested["action"] == "request_adapter_dispatch"
    assert requested["physical_effect"] is False

from shared.marketplace_ecosystem_phase12 import install_marketplace_app, register_marketplace_app
from shared.marketplace_plugin_runtime import (
    build_plugin_event_envelope,
    build_plugin_runtime_report,
    build_sandbox_runtime_context,
    plan_plugin_execution,
    validate_plugin_output,
)


def manifest(permissions=None):
    return {
        "name": "safe_irrigation_explainer",
        "version": "1.0.0",
        "author": "sahool",
        "permissions": permissions
        or ["field.read", "tiles.read", "recommendations.write", "webhooks.write"],
        "hooks": ["recommendation.before", "recommendation.after"],
        "entrypoint": "plugin.main:handler",
    }


def approved_app_and_installation(permissions=None):
    app = register_marketplace_app(manifest(permissions))["app"]
    install = install_marketplace_app(app, "11111111-1111-1111-1111-111111111111", "user-1")
    assert install["installed"] is True
    return app, install["installation"]


def test_plugin_execution_plan_allows_declared_low_risk_action():
    app, installation = approved_app_and_installation()
    result = plan_plugin_execution(
        app,
        installation,
        "recommendation.propose",
        {"field_id": "f1"},
        {"api_calls_day": 0},
        "idem-1",
    )
    assert result["allowed_to_execute"] is True
    assert result["plan"]["decision"] == "allow"
    assert result["plan"]["required_permission"] == "recommendations.write"
    assert "direct_db" in result["sandbox_context"]["denied_capabilities"]


def test_plugin_execution_denies_missing_permission_and_quota_exceeded():
    app, installation = approved_app_and_installation(["field.read"])
    missing = plan_plugin_execution(app, installation, "recommendation.propose", {}, {}, "idem-2")
    assert missing["plan"]["decision"] == "deny"
    assert "permission_denied" in missing["plan"]["reasons"]

    app2, installation2 = approved_app_and_installation(["tiles.read"])
    blocked = plan_plugin_execution(
        app2, installation2, "raster.tile.read", {}, {"tiles_day": 50_000}, "idem-3"
    )
    assert blocked["plan"]["decision"] == "deny"
    assert "quota_exceeded" in blocked["plan"]["reasons"]


def test_sensitive_action_requires_review_not_direct_execution():
    app = register_marketplace_app(manifest(["field.read", "autonomy.dispatch"]))["app"]
    # Simulate approved app after manual security review.
    app["status"] = "approved"
    installation = install_marketplace_app(app, "11111111-1111-1111-1111-111111111111", "admin")[
        "installation"
    ]
    result = plan_plugin_execution(app, installation, "autonomy.dispatch.request", {}, {}, "idem-4")
    assert result["allowed_to_execute"] is False
    assert result["plan"]["decision"] == "review"
    assert "requires_human_approval" in result["plan"]["reasons"]


def test_sandbox_context_never_exposes_raw_infrastructure_credentials():
    app, installation = approved_app_and_installation()
    ctx = build_sandbox_runtime_context(app, installation, "field.context.read")
    assert "DATABASE_URL" not in ctx["runtime_env"]
    assert "NATS_URL" not in ctx["runtime_env"]
    assert ctx["capabilities"]["filesystem"] == "read_only"


def test_plugin_output_validation_blocks_direct_side_effects():
    app, installation = approved_app_and_installation()
    plan = plan_plugin_execution(app, installation, "recommendation.propose", {}, {}, "idem-5")[
        "plan"
    ]
    safe = validate_plugin_output(plan, {"effects": [{"kind": "recommendation_proposal"}]})
    assert safe["valid"] is True
    unsafe = validate_plugin_output(
        plan, {"effects": [{"kind": "direct_db_write"}, {"kind": "actuator_command"}]}
    )
    assert unsafe["valid"] is False
    assert "direct_db_write" in unsafe["blocked_effects"]
    assert "actuator_command" in unsafe["blocked_effects"]


def test_plugin_event_envelope_sanitizes_secrets_and_rejects_unknown_events():
    app, installation = approved_app_and_installation()
    plan = plan_plugin_execution(app, installation, "webhook.emit", {}, {}, "idem-6")["plan"]
    env = build_plugin_event_envelope(
        plan, "plugin.recommendation.proposed", {"ok": 1, "token": "secret"}
    )
    assert env["created"] is True
    assert "token" not in env["envelope"]["payload"]
    bad = build_plugin_event_envelope(plan, "not.allowed", {})
    assert bad["created"] is False


def test_plugin_runtime_report_summarizes_actions():
    app, installation = approved_app_and_installation()
    report = build_plugin_runtime_report(
        app, installation, ["field.context.read", "recommendation.propose"]
    )
    assert report["summary"]["actions_checked"] == 2
    assert report["summary"]["has_denied"] is False

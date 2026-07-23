from shared.marketplace_ecosystem_phase12 import (
    build_developer_portal_index,
    build_graphql_facade_schema,
    build_plugin_sandbox_policy,
    build_public_sdk_manifest,
    create_webhook_subscription,
    define_connector_descriptor,
    enforce_plugin_permission,
    enforce_quota,
    install_marketplace_app,
    plan_webhook_delivery,
    record_usage,
    register_marketplace_app,
    run_phase12_ecosystem_cycle,
    sign_webhook_payload,
    validate_plugin_manifest,
)


def safe_manifest(**overrides):
    manifest = {
        "name": "irrigation_optimizer",
        "version": "1.0.0",
        "author": "sahool",
        "description": "Optimizes irrigation recommendations.",
        "permissions": ["field.read", "weather.read", "recommendations.write"],
        "hooks": ["recommendation.before", "recommendation.after"],
        "entrypoint": "plugin.main:handler",
        "billing_meter": "api_calls_day",
    }
    manifest.update(overrides)
    return manifest


def test_manifest_validation_accepts_safe_plugin():
    review = validate_plugin_manifest(safe_manifest())
    assert review["valid"] is True
    assert review["risk_level"] in {"low", "medium"}
    assert not review["findings"]


def test_manifest_validation_flags_unknown_permission_and_sensitive_review():
    review = validate_plugin_manifest(
        safe_manifest(permissions=["field.read", "actuator.write", "unknown.scope"])
    )
    assert review["valid"] is False
    assert "actuator.write" in review["sensitive_permissions"]
    assert review["requires_security_review"] is True
    assert review["unknown_permissions"] == ["unknown.scope"]


def test_marketplace_registration_and_installation_flow():
    registration = register_marketplace_app(safe_manifest())
    assert registration["app"]["status"] == "approved"
    install = install_marketplace_app(
        registration["app"], tenant_id="tenant-1", installed_by="user-1"
    )
    assert install["installed"] is True
    assert "field.read" in install["installation"]["granted_permissions"]


def test_install_rejects_unapproved_sensitive_app():
    registration = register_marketplace_app(
        safe_manifest(permissions=["field.read", "actuator.write"])
    )
    assert registration["app"]["status"] == "review"
    install = install_marketplace_app(
        registration["app"], tenant_id="tenant-1", installed_by="user-1"
    )
    assert install["installed"] is False
    assert install["reason"] == "app_not_approved"


def test_permission_enforcement_is_fail_closed():
    registration = register_marketplace_app(safe_manifest())
    install = install_marketplace_app(
        registration["app"], tenant_id="tenant-1", installed_by="user-1"
    )
    installation = install["installation"]
    assert enforce_plugin_permission(installation, "field.read")["allowed"] is True
    denied = enforce_plugin_permission(installation, "billing.write")
    assert denied["allowed"] is False
    assert denied["reason"] == "permission_denied"


def test_sandbox_policy_requires_human_approval_for_actuation():
    policy = build_plugin_sandbox_policy({"permissions": ["field.read", "actuator.write"]})
    assert policy["actuation_allowed"] is True
    assert policy["human_approval_required_for_actuation"] is True
    assert policy["audit_level"] == "elevated"


def test_webhook_subscription_requires_https_and_known_events():
    bad = create_webhook_subscription(
        "tenant-1", "http://evil.example/hook", ["field.updated"], "secret/ref"
    )
    assert bad["created"] is False
    good = create_webhook_subscription(
        "tenant-1", "https://example.com/hook", ["field.updated"], "secret/ref"
    )
    assert good["created"] is True
    unknown = create_webhook_subscription(
        "tenant-1", "https://example.com/hook", ["not.real"], "secret/ref"
    )
    assert unknown["created"] is False


def test_webhook_delivery_signs_payload_and_ignores_unsubscribed_event():
    sub = create_webhook_subscription(
        "tenant-1", "https://example.com/hook", ["field.updated"], "secret/ref"
    )["webhook"]
    ignored = plan_webhook_delivery(sub, "alert.created", {"x": 1}, "secret")
    assert ignored["status"] == "ignored"
    delivery = plan_webhook_delivery(sub, "field.updated", {"field_id": "f1"}, "secret")
    assert delivery["status"] == "pending"
    assert delivery["headers"]["X-Sahool-Signature"].startswith("sha256=")
    assert (
        sign_webhook_payload(delivery["envelope"], "secret")
        == delivery["headers"]["X-Sahool-Signature"]
    )


def test_connector_descriptor_supports_erp_equipment_and_iot_contracts():
    descriptor = define_connector_descriptor(
        "John Deere",
        "equipment",
        ["machine.sync", "field.boundary.sync"],
        required_permissions=["field.read", "operations.write"],
    )
    assert descriptor["valid"] is True
    assert descriptor["connector"]["connector_type"] == "equipment"
    invalid = define_connector_descriptor("Mystery", "unknown", [])
    assert invalid["valid"] is False


def test_sdk_graphql_and_portal_contracts_are_generated():
    sdk = build_public_sdk_manifest("https://api.example.com/")
    gql = build_graphql_facade_schema()
    portal = build_developer_portal_index()
    assert "python" in sdk["languages"]
    assert "Field" in gql["types"]
    assert any(section["slug"] == "plugins" for section in portal["sections"])


def test_usage_metering_and_quota_enforcement():
    usage = record_usage("tenant-1", "app-1", "api_calls_day", 5, "idem-1")
    assert usage["recorded"] is True
    assert record_usage("tenant-1", "app-1", "api_calls_day", -1, "idem-2")["recorded"] is False
    installation = {"quota": {"api_calls_day": 10}}
    allowed = enforce_quota(installation, {"api_calls_day": 4}, {"api_calls_day": 5})
    blocked = enforce_quota(installation, {"api_calls_day": 9}, {"api_calls_day": 5})
    assert allowed["allowed"] is True
    assert blocked["allowed"] is False
    assert blocked["violations"] == ["api_calls_day"]


def test_full_phase12_cycle_produces_ecosystem_artifacts():
    cycle = run_phase12_ecosystem_cycle(safe_manifest())
    assert cycle["cycle_id"].startswith("ecosystem_")
    assert cycle["registration"]["app"]["status"] == "approved"
    assert cycle["installation"]["installed"] is True
    assert cycle["delivery_plan"]["status"] == "pending"
    assert cycle["quota"]["allowed"] is True

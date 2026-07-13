from datetime import UTC, datetime, timedelta, timezone

import pytest
from api.irrigation_commissioning_certification import (
    REQUIRED_EVIDENCE_TYPES,
    REQUIRED_SAFETY_CHECKS,
    apply_commissioning_executability_gate,
    build_commissioning_evidence,
    build_irrigation_commissioning_certification,
)

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)
HASH = "a" * 64
GRAPH_DIGEST = "b" * 64
HANDSHAKE_DIGEST = "c" * 64


def evidence_set(*, stale=False, flow=42.0, pressure=2.6, power=31.0):
    observed = NOW - (timedelta(days=400) if stale else timedelta(days=1))
    values = {
        "installation_identity": {"serial_number": "PX-1"},
        "pump_flow_test": {"measured_flow_lps": flow},
        "pressure_test": {"measured_terminal_pressure_bar": pressure},
        "controller_handshake": {"handshake_digest": HANDSHAKE_DIGEST},
        "safety_interlock_test": {"all_passed": True},
        "energy_system_test": {"measured_power_kw": power},
        "signed_acceptance": {"accepted": True},
    }
    return [
        build_commissioning_evidence(
            tenant_id="t1",
            project_id="p1",
            field_id="f1",
            machine_id="m1",
            evidence_type=evidence_type,
            status="verified",
            observed_at=observed,
            captured_by="tech-1",
            witness_id="witness-1",
            source_uri=f"s3://evidence/{evidence_type}.json",
            source_hash=HASH,
            values=values[evidence_type],
        )
        for evidence_type in sorted(REQUIRED_EVIDENCE_TYPES)
    ]


def safety_checks():
    return {name: True for name in REQUIRED_SAFETY_CHECKS}


def certification(**overrides):
    kwargs = dict(
        tenant_id="t1",
        project_id="p1",
        field_id="f1",
        season_id="s1",
        machine_id="m1",
        controller_id="c1",
        energy_system_id="e1",
        irrigation_capability_digest=GRAPH_DIGEST,
        evidence=evidence_set(),
        safety_checks=safety_checks(),
        certification_status="certified",
        now=NOW,
        certified_at=NOW - timedelta(days=2),
        valid_until=NOW + timedelta(days=365),
        signed_by="installer-1",
        reviewed_by="reviewer-1",
        design_flow_lps=45,
        design_terminal_pressure_bar=2.5,
        maximum_power_kw=40,
    )
    kwargs.update(overrides)
    return build_irrigation_commissioning_certification(**kwargs)


def graph(**overrides):
    value = {
        "tenant_id": "t1",
        "project_id": "p1",
        "field_id": "f1",
        "season_id": "s1",
        "machine_id": "m1",
        "controller_id": "c1",
        "energy_system_id": "e1",
        "status": "verified",
        "operational_eligible": True,
        "capability_digest": GRAPH_DIGEST,
        "blocking_reasons": [],
    }
    value.update(overrides)
    return value


def test_verified_commissioning_allows_executability_gate():
    cert = certification()
    assert cert.status == "certified"
    assert cert.operational_eligible
    assert len(cert.certification_digest) == 64
    gate = apply_commissioning_executability_gate(capability_graph=graph(), certification=cert)
    assert gate["status"] == "executable"
    assert gate["execution_allowed"] is True
    assert len(gate["executability_digest"]) == 64


def test_missing_required_evidence_blocks_certification():
    items = [item for item in evidence_set() if item.evidence_type != "pressure_test"]
    cert = certification(evidence=items)
    assert not cert.operational_eligible
    assert "PRESSURE_TEST_EVIDENCE_REQUIRED" in cert.blocking_reasons


def test_stale_evidence_blocks_certification():
    cert = certification(evidence=evidence_set(stale=True))
    assert not cert.operational_eligible
    assert any(reason.endswith("EVIDENCE_STALE") for reason in cert.blocking_reasons)


def test_failed_safety_interlock_blocks_certification():
    checks = safety_checks()
    checks["emergency_stop"] = False
    cert = certification(safety_checks=checks)
    assert "SAFETY_CHECK_EMERGENCY_STOP_REQUIRED" in cert.blocking_reasons


def test_below_acceptance_flow_and_pressure_block():
    cert = certification(evidence=evidence_set(flow=20, pressure=1.0))
    assert "COMMISSIONED_FLOW_BELOW_ACCEPTANCE_THRESHOLD" in cert.blocking_reasons
    assert "COMMISSIONED_PRESSURE_BELOW_ACCEPTANCE_THRESHOLD" in cert.blocking_reasons


def test_expired_certification_blocks_gate():
    cert = certification(valid_until=NOW - timedelta(seconds=1))
    assert "COMMISSIONING_CERTIFICATION_EXPIRED" in cert.blocking_reasons
    gate = apply_commissioning_executability_gate(capability_graph=graph(), certification=cert)
    assert gate["execution_allowed"] is False


def test_digest_mismatch_blocks_gate():
    cert = certification()
    gate = apply_commissioning_executability_gate(
        capability_graph=graph(capability_digest="d" * 64),
        certification=cert,
    )
    assert not gate["execution_allowed"]
    assert "COMMISSIONING_CAPABILITY_DIGEST_MISMATCH" in gate["blocking_reasons"]


def test_independent_reviewer_is_mandatory():
    cert = certification(signed_by="same", reviewed_by="same")
    assert "INDEPENDENT_REVIEWER_MUST_DIFFER" in cert.blocking_reasons


pytestmark = pytest.mark.unit

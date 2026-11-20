"""Validate the JUnit cases actually written by the certifying pytest process."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

LIVE = {
    "test_reservation_mqtt_replay_has_one_simulated_device_effect",
    "test_gate_a_reservation_over_live_postgres",
    "test_gate_a_two_connection_advisory_lock_serializes",
    "test_gate_a_concurrent_overcommit_serialized_rejection",
    "test_gate_a_idempotent_replay_is_rejected_no_duplicate",
    "test_gate_b1_dispatch_intent_emitted_to_outbox_atomically",
}
FRESH = {
    "test_rls_roles_are_not_privileged",
    "test_v195_tables_rls_and_force_rls_are_enabled",
    "test_missing_tenant_context_is_fail_closed",
    "test_reader_is_scoped_and_cannot_write",
    "test_event_correlation_id_is_not_nullable",
    "test_event_unique_constraint_treats_null_causation_as_not_distinct",
}
UPGRADE = {
    "test_u1_upgrade_left_the_v195_v196_surface_present",
    "test_u1_legacy_capability_survived_and_is_tenant_visible",
    "test_u1_reservation_binds_v195_composite_fk_over_legacy_capability",
}


def validate(report: Path, suite: str) -> None:
    expected = {"test_irr_f01_reservation_live_pg": LIVE}
    if suite == "fresh":
        expected["test_v195_postgres"] = FRESH
    elif suite == "upgrade":
        expected["test_irr_f01_upgrade_gate_u1_pg"] = UPGRADE
    else:
        raise ValueError(f"unknown irrigation suite: {suite}")
    cases = ET.parse(report).findall(".//testcase")
    observed = set()
    for case in cases:
        name = case.get("name")
        if any(case.find(tag) is not None for tag in ("failure", "skipped", "error")):
            raise ValueError(f"mandatory suite contains an unsuccessful case: {name}")
        observed.add((case.get("classname", "").split(".")[-1], name))
    missing = {(module, name) for module, names in expected.items() for name in names} - observed
    if missing:
        raise ValueError(f"missing JUnit cases: {sorted(missing)}")


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    # JUnit writes the report inside its sessionfinish hook; check after it returns.
    yield
    if exitstatus == 0:
        try:
            validate(Path(session.config.option.xmlpath), os.environ["IRR_F01_SUITE"])
        except (OSError, ET.ParseError, ValueError, TypeError) as exc:
            session.config.get_terminal_writer().line(f"IRR-F01 certification failed: {exc}")
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

"""Certify raster cases from the JUnit path selected by the pytest process."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.ci import live_pg_evidence_guard

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "docs/architecture"
SCHEMA_CONTRACTS = {
    15: CONTRACT_DIR / "raster_live_pg_schema_contract.json",
    16: CONTRACT_DIR / "raster_live_pg16_schema_contract.json",
}

REQUIRED_CASES = {
    (
        "test_raster_batch_postgres_integration",
        "test_database_connection_uses_an_unprivileged_nonowner_role",
    ),
    (
        "test_raster_batch_postgres_integration",
        "test_real_postgres_dual_worker_recovery_and_fencing",
    ),
    (
        "test_raster_batch_postgres_integration",
        "test_distinct_claim_cannot_reuse_an_existing_job_id",
    ),
    (
        "test_raster_batch_postgres_integration",
        "test_concurrent_claims_share_one_lease_and_one_attempt[2]",
    ),
    (
        "test_raster_batch_postgres_integration",
        "test_concurrent_claims_share_one_lease_and_one_attempt[8]",
    ),
    (
        "test_single_scene_concurrent_pg",
        "test_concurrent_enqueue_leaves_one_item_and_no_orphan_run[2]",
    ),
    (
        "test_single_scene_concurrent_pg",
        "test_concurrent_enqueue_leaves_one_item_and_no_orphan_run[8]",
    ),
}


def pytest_addoption(parser):
    parser.addoption(
        "--raster-pg-major",
        type=int,
        choices=(15, 16),
        default=15,
        help="Expected PostgreSQL server major for raster certification",
    )


def validate(report: Path) -> None:
    """Require each live case once and reject unsuccessful cases in the report."""
    with report.open(encoding="utf-8") as stream:
        cases = ET.parse(stream).findall(".//testcase")
    if not cases:
        raise ValueError("empty JUnit report: no test cases")
    observed = set()
    for case in cases:
        name = case.get("name", "")
        identity = (case.get("classname", "").split(".")[-1], name)
        if any(case.find(tag) is not None for tag in ("failure", "skipped", "error")):
            raise ValueError(f"mandatory suite contains an unsuccessful case: {name}")
        if identity in observed:
            raise ValueError(f"duplicate JUnit case: {identity}")
        observed.add(identity)
    missing = REQUIRED_CASES - observed
    if missing:
        raise ValueError(f"missing JUnit cases: {sorted(missing)}")


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    # The inner JUnit hook writes its report; the lab shim can change xmlpath.
    yield
    if exitstatus != pytest.ExitCode.OK or session.exitstatus != pytest.ExitCode.OK:
        return
    try:
        report = Path(session.config.option.xmlpath)
        validate(report)
        result = live_pg_evidence_guard.main(
            [
                "--junit",
                str(report),
                "--min-executed",
                str(len(REQUIRED_CASES)),
                "--evidence",
                str(report.with_suffix(".evidence.json")),
                "--schema-contract",
                str(SCHEMA_CONTRACTS[session.config.option.raster_pg_major]),
            ]
        )
        if result != 0:
            raise ValueError(f"live PostgreSQL evidence guard returned {result}")
    except (OSError, ET.ParseError, ValueError, TypeError, SystemExit) as exc:
        session.config.get_terminal_writer().line(f"Raster PG certification failed: {exc}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED

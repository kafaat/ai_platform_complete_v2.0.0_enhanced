"""The raster gate must certify the actual JUnit output before probing PostgreSQL."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest

from scripts.raster_pg import required_cases

pytestmark = pytest.mark.unit

# Independent fixture: removing a required case from the adapter must fail a test.
LIVE_CASES = [
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
]


def _report(path, cases=LIVE_CASES, unsuccessful=None):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", tests=str(len(cases)))
    for module, name in cases:
        case = ET.SubElement(
            suite, "testcase", classname=f"services.raster-service.{module}", name=name
        )
    if unsuccessful is not None:
        ET.SubElement(case, unsuccessful)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _session(path, status=pytest.ExitCode.OK):
    writer = Mock()
    config = SimpleNamespace(
        option=SimpleNamespace(xmlpath=str(path), raster_pg_major=15),
        get_terminal_writer=lambda: writer,
    )
    return SimpleNamespace(config=config, exitstatus=status), writer


def _finish(session, exitstatus=pytest.ExitCode.OK):
    """Resume the wrapper around the inner hooks, without running real PG probes."""
    hook = required_cases.pytest_sessionfinish(session, exitstatus)
    next(hook)
    with pytest.raises(StopIteration):
        next(hook)


@pytest.fixture
def evidence_guard(monkeypatch):
    guard = Mock(return_value=0)
    monkeypatch.setattr(required_cases.live_pg_evidence_guard, "main", guard)
    return guard


@pytest.mark.parametrize(
    ("major", "contract"),
    [
        (15, "raster_live_pg_schema_contract.json"),
        (16, "raster_live_pg16_schema_contract.json"),
    ],
)
def test_complete_report_reaches_existing_guard_with_actual_junit_path(
    tmp_path, evidence_guard, major, contract
):
    stale_path = tmp_path / "ci-requested.xml"
    actual_path = tmp_path / "lab-selected.junit.xml"
    session, writer = _session(stale_path)
    session.config.option.raster_pg_major = major
    hook = required_cases.pytest_sessionfinish(session, pytest.ExitCode.OK)

    next(hook)
    evidence_guard.assert_not_called()
    assert not actual_path.exists()
    # Simulate JUnit writing after the shim has selected its own report path.
    session.config.option.xmlpath = str(actual_path)
    _report(actual_path)
    with pytest.raises(StopIteration):
        next(hook)

    assert session.exitstatus == pytest.ExitCode.OK
    writer.line.assert_not_called()
    evidence_guard.assert_called_once_with(
        [
            "--junit",
            str(actual_path),
            "--min-executed",
            "7",
            "--evidence",
            str(actual_path.with_suffix(".evidence.json")),
            "--schema-contract",
            str(Path(__file__).resolve().parents[1] / "docs/architecture" / contract),
        ]
    )
    assert not stale_path.exists()


@pytest.mark.parametrize("missing", LIVE_CASES, ids=[name for _, name in LIVE_CASES])
def test_each_required_case_is_enforced_before_guard(tmp_path, evidence_guard, missing):
    path = tmp_path / "report.xml"
    _report(path, cases=[case for case in LIVE_CASES if case != missing])
    session, writer = _session(path)

    _finish(session)

    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    evidence_guard.assert_not_called()
    assert "missing JUnit cases" in writer.line.call_args.args[0]
    assert missing[1] in writer.line.call_args.args[0]
    assert not path.with_suffix(".evidence.json").exists()


@pytest.mark.parametrize("outcome", ["skipped", "failure", "error"])
def test_unsuccessful_case_never_reaches_guard(tmp_path, evidence_guard, outcome):
    path = tmp_path / "report.xml"
    _report(path, unsuccessful=outcome)
    session, writer = _session(path)

    _finish(session)

    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    evidence_guard.assert_not_called()
    assert "unsuccessful case" in writer.line.call_args.args[0]
    assert not path.with_suffix(".evidence.json").exists()


@pytest.mark.parametrize("problem", ["duplicate", "empty", "missing", "corrupt", "wrong-module"])
def test_invalid_report_never_reaches_guard(tmp_path, evidence_guard, problem):
    path = tmp_path / "report.xml"
    if problem == "duplicate":
        _report(path, cases=[*LIVE_CASES, LIVE_CASES[0]])
    elif problem == "empty":
        _report(path, cases=[])
    elif problem == "corrupt":
        path.write_text("<testsuites>", encoding="utf-8")
    elif problem == "wrong-module":
        _report(path, cases=[("unrelated_test_module", name) for _, name in LIVE_CASES])
    session, writer = _session(path)

    _finish(session)

    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    evidence_guard.assert_not_called()
    writer.line.assert_called_once()
    assert not path.with_suffix(".evidence.json").exists()


@pytest.mark.parametrize("failure", ["nonzero", "exit"])
def test_guard_failure_fails_the_pytest_session(tmp_path, evidence_guard, failure):
    path = tmp_path / "report.xml"
    _report(path)
    if failure == "nonzero":
        evidence_guard.return_value = 1
    else:
        evidence_guard.side_effect = required_cases.live_pg_evidence_guard.GuardExit(
            "PostgreSQL probe unavailable", "PSQL_CATALOGUE_QUERY_FAILED"
        )
    session, writer = _session(path)

    _finish(session)

    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    evidence_guard.assert_called_once()
    writer.line.assert_called_once()


@pytest.mark.parametrize("original_failure", [True, False], ids=["pytest", "inner-hook"])
def test_existing_failure_is_preserved_without_certification(
    tmp_path, evidence_guard, original_failure
):
    path = tmp_path / "report.xml"
    _report(path)
    session, writer = _session(path, status=pytest.ExitCode.INTERRUPTED)

    _finish(
        session,
        exitstatus=pytest.ExitCode.INTERRUPTED if original_failure else pytest.ExitCode.OK,
    )

    assert session.exitstatus == pytest.ExitCode.INTERRUPTED
    evidence_guard.assert_not_called()
    writer.line.assert_not_called()


def test_unconfigured_junit_fails_closed(tmp_path, evidence_guard):
    session, writer = _session(tmp_path / "report.xml")
    session.config.option.xmlpath = None

    _finish(session)

    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    evidence_guard.assert_not_called()
    writer.line.assert_called_once()

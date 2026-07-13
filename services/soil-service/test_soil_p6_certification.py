from copy import deepcopy

from p6_certification import evaluate_run, verify_manifest

from shared.contracts.soil.p6 import (
    CertificationCheck,
    CertificationEvidence,
    RuntimeCertificationRun,
)


def _run(status="passed"):
    names = [
        "migrations",
        "rls",
        "concurrency",
        "lease_recovery",
        "retry_dead_letter",
        "e2e",
        "lineage",
        "performance",
        "calibration",
        "rollback",
    ]
    evidence = []
    checks = []
    for n in names:
        e = CertificationEvidence(
            check_name=n, evidence_type="test", sha256="a" * 64, summary={"ok": True}
        )
        evidence.append(e)
        checks.append(CertificationCheck(check_name=n, status=status, evidence_ids=[e.evidence_id]))
    return RuntimeCertificationRun(
        tenant_id="00000000-0000-0000-0000-000000000001",
        release_ref="r1",
        environment="staging",
        migrations_applied_through="v166",
        checks=checks,
        evidence=evidence,
        approvals=["soil-owner", "security-owner"],
    )


def test_p6_certifies_only_complete_dual_approved_run():
    run = evaluate_run(_run())
    assert run.status == "certified" and not run.blockers and verify_manifest(run)


def test_p6_fails_closed_for_missing_evidence_or_failed_check():
    run = _run()
    run.checks[2].status = "failed"
    run.checks[3].evidence_ids = ["missing"]
    run = evaluate_run(run)
    assert run.status == "blocked"
    assert "check_not_passed:concurrency" in run.blockers
    assert any(x.startswith("unknown_evidence:lease_recovery") for x in run.blockers)


def test_manifest_detects_tampering():
    run = evaluate_run(_run())
    assert verify_manifest(run)
    run.release_ref = "tampered"
    assert not verify_manifest(run)

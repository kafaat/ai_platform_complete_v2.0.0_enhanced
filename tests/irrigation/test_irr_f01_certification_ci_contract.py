"""Static guard preventing a green-but-skipped IRR-F01 certification job.

The live reservation gates only certify anything when they actually EXECUTE against a real
NOSUPERUSER/NOBYPASSRLS role with IRR_F01_CERTIFICATION_REQUIRED=1. This guard fails fast if
the CI wiring (dedicated role, distinct admin/app DSNs, fail-closed env) or the live test's
fail-closed switch regresses — so certification can never quietly degrade back to a skip.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
LIVE = ROOT / "tests_v9" / "test_irr_f01_reservation_live_pg.py"
UPGRADE = ROOT / "tests_v9" / "test_irr_f01_upgrade_gate_u1_pg.py"
U1_SCRIPT = ROOT / "scripts" / "irr_f01" / "upgrade_gate_u1.sh"


def test_ci_uses_distinct_admin_and_nobypassrls_app_dsns():
    text = CI.read_text(encoding="utf-8")
    assert "CREATE ROLE sahool_app_test" in text
    assert "NOSUPERUSER NOBYPASSRLS" in text
    assert "TEST_DATABASE_ADMIN_URL: postgresql://sahool_test:" in text
    assert "TEST_DATABASE_URL: postgresql://sahool_app_test:" in text
    assert 'IRR_F01_CERTIFICATION_REQUIRED: "1"' in text
    assert 'test "$role_flags" = "false:false"' in text


def test_live_gate_fails_in_certification_mode_instead_of_skipping():
    text = LIVE.read_text(encoding="utf-8")
    assert "CERTIFICATION_REQUIRED" in text
    assert "pytest.fail(message)" in text
    assert '_skip_or_fail("connect as a NOSUPERUSER/NOBYPASSRLS' in text


def test_live_gate_is_fail_closed_on_missing_driver_and_admin_dsn():
    # A plain importorskip / silent admin-DSN fallback would let certification pass green with
    # asyncpg absent or admin/app roles collapsed — lock both fail-closed switches in place.
    text = LIVE.read_text(encoding="utf-8")
    assert "if CERTIFICATION_REQUIRED:\n        raise" in text  # missing driver → raise, not skip
    assert "TEST_DATABASE_ADMIN_URL unset — certification requires a distinct admin DSN" in text
    assert "app role must be NOINHERIT" in text
    # The window is future-anchored (no rotting past constant) and RLS refusal is proven by code.
    assert "datetime.now(UTC) + timedelta(hours=1)" in text
    assert 'rls_exc.value.sqlstate == "42501"' in text


def test_ci_runs_the_concurrent_overcommit_gate_a():
    # The end-to-end concurrent overcommit proof (T1 commits, T2 re-reads and is rejected)
    # must exist and ride the same live module the certification steps run.
    text = LIVE.read_text(encoding="utf-8")
    assert "test_gate_a_concurrent_overcommit_serialized_rejection" in text
    assert "after_locks_acquired" in text
    assert 'blocking_code == "CONCURRENT_LOAD_EXCEEDED"' in text


def test_ci_runs_the_v194_upgrade_certification_gate_u1():
    text = CI.read_text(encoding="utf-8")
    assert "scripts/irr_f01/upgrade_gate_u1.sh" in text
    assert "IRR_F01_UPGRADE_DATABASE_URL" in text
    assert UPGRADE.exists(), "Gate U1 upgrade test module must exist"
    assert U1_SCRIPT.exists(), "Gate U1 upgrade build script must exist"
    upgrade_text = UPGRADE.read_text(encoding="utf-8")
    # The upgrade module must be fail-closed under certification mode, like the live module.
    assert "CERTIFICATION_REQUIRED" in upgrade_text
    assert "pytest.fail(message)" in upgrade_text
    script_text = U1_SCRIPT.read_text(encoding="utf-8")
    # It must genuinely stop at v194 and then apply the upgrade — not just run the full chain.
    assert "v195_*|v196_*" in script_text
    assert "idempotent re-apply" in script_text

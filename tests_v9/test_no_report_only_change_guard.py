import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def _run(*paths):
    return subprocess.run(
        [sys.executable, "scripts/ci/no_report_only_change_guard.py", *paths],
        text=True,
        capture_output=True,
    )


def test_report_only_change_is_blocked():
    result = _run("FOO_REPORT_20260709.md", "route_inventory.generated.json")
    assert result.returncode != 0
    assert "report-only" in result.stderr


def test_report_with_guard_change_is_allowed():
    result = _run("FOO_REPORT_20260709.md", "scripts/ci/example_guard.py")
    assert result.returncode == 0, result.stderr


def test_runbook_only_is_substantive_for_certification_path():
    result = _run("docs/runbooks/PRODUCTION_EVIDENCE_PACK.md")
    assert result.returncode == 0, result.stderr


def test_migration_change_is_substantive():
    # A migration fix (e.g. making DDL idempotent) accompanied only by the
    # regenerated release bundle must NOT be blocked as report-only — migrations
    # are schema/data code. Regression guard for the v205 idempotency fix PR.
    result = _run(
        "migrations/v205_irrigation_reservation_runtime_hardening.sql",
        "release/FILE_CHECKSUMS.sha256",
        "sahool-brain/gaps/registry.md",
    )
    assert result.returncode == 0, result.stderr


def test_architecture_test_change_is_substantive():
    # Architecture tests live under tests/ (not tests_v9/). Adding a real test plus
    # the regenerated mapping report must NOT be blocked as report-only.
    result = _run(
        "tests/architecture/test_runtime_identity_bridge.py",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode == 0, result.stderr


def test_runtime_verification_spec_change_is_substantive():
    # A functional probe plan / identity-bridge map is a behavioural governance spec,
    # not a report; changing it alongside the regenerated bundle must be allowed.
    result = _run(
        "runtime-verification/functional_probes/sahool-platform.json",
        "runtime-verification/service_identity_map.json",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr


def test_brain_maintenance_is_docs_not_report_only():
    # The mandated end-of-session brain update — even the brain's own gaps/registry.md
    # (whose name matches the REGISTRY hint) plus the regenerated release manifest — is
    # documentation, not a certification report, and must NOT be blocked.
    result = _run(
        "sahool-brain/log.md",
        "sahool-brain/gaps/registry.md",
        "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
    )
    assert result.returncode == 0, result.stderr


def test_capabilities_registry_report_still_blocked():
    # The exemption is scoped to sahool-brain/: the capabilities/ certification registry
    # and generated mapping reports remain report-like and blocked without substantive code.
    result = _run(
        "capabilities/registry/capabilities.json",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode != 0
    assert "report-only" in result.stderr


def test_frontend_code_with_generated_report_is_substantive():
    # False positive مقيس على PR #857: إصلاح UI حقيقيّ (TSX) + مصنوعات مولَّدة
    # حُجب «report-only» لأنّ التصنيف الأوّل لم يعرف frontend/ ككود.
    result = _run(
        "frontend/src/hooks/useApi.ts",
        "frontend/src/components/ds/theme.tsx",
        "release/FILE_CHECKSUMS.sha256",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode == 0, result.stderr


def test_mobile_code_with_generated_report_is_substantive():
    # نفس العيب كان سيصيب PR يعدّل Flutter/mobile مع تقرير مولَّد فقط.
    result = _run(
        "mobile/lib/screens/field_ranking.dart",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr


def test_service_code_with_generated_report_is_substantive():
    result = _run(
        "services/sahool-platform/api/routers/nl_sql.py",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode == 0, result.stderr


def test_plain_docs_outside_certification_path_pass():
    # وثيقة عاديّة بلا تلميح تقرير خارج مسار الاعتماد ليست report-like أصلاً.
    result = _run("docs/adr/0001-topology.md")
    assert result.returncode == 0, result.stderr

#!/usr/bin/env python3
"""Build a deterministic Sahool release inventory/checksum bundle.

This script is intentionally dependency-free. It does not build Docker images;
it validates and records the source release assets that must exist before a
runtime deployment can start.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# نفس اصطلاح `generated_artifact_contract` في `scripts/ci/`: مسار مطلق لا حزمة —
# المستودع بلا `__init__.py` هناك، والاستيراد النسبيّ ينكسر حسب مجلّد التشغيل.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))

from deterministic_time import generated_at_utc  # noqa: E402

EXCLUDE_DIRS = {
    ".git",
    ".claude",  # إعدادات أدوات محلّيّة (settings.local.json) تتغيّر لكلّ بيئة — خارج بصمة الإصدار
    "sahool-brain",  # قاعدة معرفة الوكيل (وثائق تتغيّر كلّ جلسة) — ليست أصلاً قابلاً للنشر؛ خارج بصمة الإصدار
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".dart_tool",
    "evidence-lab",  # نواتج تشغيل متغيّرة؛ تصميم المختبر نفسه يبقى داخل بصمة الإصدار
    "build",
    "dist",
    ".venv",
    "venv",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}
REQUIRED_FILES = [
    "VERSION",
    "docker-compose.v9.yml",
    "migrations/MANIFEST.txt",
    "scripts/production_validation_gate.sh",
    "scripts/security/rls_runtime_gate.py",
    "scripts/security/validate_rls_write_policies.py",
    "scripts/observability/validate_observability_assets.py",
    "scripts/check_gateway_routes.sh",
    "scripts/runtime_smoke.sh",
    "scripts/e2e/e2e_field_imagery_ai.sh",
    "scripts/load/run_load_tests.sh",
    "scripts/chaos/run_chaos_tests.sh",
    "scripts/recovery/recovery_smoke.sh",
    "scripts/ci/validate_ci_gates.py",
    "scripts/ci/unified_production_readiness_gate.py",
    "scripts/ci/container_image_pin_guard.py",
    "scripts/ci/release_attestation_guard.py",
    "scripts/ci/secret_history_scan_guard.py",
    "scripts/ci/github_actions_policy_guard.py",
    "scripts/ci/local_test_dependency_preflight.py",
    "scripts/release/scan_release_archive.py",
    "scripts/ci/frontend_reproducibility_guard.py",
    "config/security_exceptions.json",
    "scripts/release/verify_attested_artifact.sh",
    "scripts/ci/scene_provenance_ui_guard.py",
    "scripts/release/generate_dependency_sbom.py",
    "scripts/qdrant/snapshot_manager.py",
    "scripts/simulation/sim_golden.py",
    "scripts/ci/local_quality_gate.sh",
    "scripts/ci/raster_quality_gate.sh",
    "scripts/runtime/env_doctor.py",
    "scripts/runtime/runtime_doctor.sh",
    "scripts/migrations/validate_migration_manifest.py",
    "migrations/v113_phase_runtime_workers_jobs.sql",
    "services/sahool-platform/api/phase_runtime_workers.py",
    "shared/runtime_worker_contracts.py",
    "scripts/workers/run_phase_runtime_worker.sh",
    ".github/workflows/sahool-production-gates.yml",
    ".github/workflows/qdrant-backup-restore-drill.yml",
    ".github/workflows/scene-provenance-ui.yml",
    ".github/workflows/sim-golden-certification.yml",
    ".github/workflows/release-artifact-attestation.yml",
    ".github/workflows/runtime-image-provenance.yml",
    ".github/workflows/path3-runtime-verification.yml",
    ".github/workflows/runtime-verification-promotion.yml",
    "scripts/ci/runtime_verification_apply.py",
    "runtime-verification/apply-ledger/README.md",
    "scripts/ci/provenance_receipt.py",
    "scripts/ci/runtime_replay_guard.py",
    "scripts/ci/prepare_attested_runtime_images.py",
    ".github/workflows/secret-history-scan.yml",
    ".github/workflows/transitive-lock-certification.yml",
    ".github/workflows/raster-service-gates.yml",
    "RUNBOOK.md",
    "scripts/architecture/legacy_path_audit.py",
    "scripts/release/platform_route_release_binding.py",
    "release/PLATFORM_ROUTE_GOVERNANCE_BINDING.json",
    "docs/architecture/generated/platform_route_governance_attestation.json",
    "scripts/architecture/build_platform_catalog.py",
    "config/platform_catalog_overrides.yml",
    "platform_catalog.generated.json",
    "runtime_capability_manifest.generated.json",
    "frontend/src/lib/platformCatalog.generated.ts",
]
REQUIRED_REPORTS = [
    "PHASE4_PRODUCTION_HARDENING_SECURITY_OBSERVABILITY_REPORT_20260626.md",
    "PHASE6_FEATURE_STORE_MODEL_REGISTRY_RUNTIME_REPORT_20260626.md",
    "PHASE7_IOT_EXECUTION_ADAPTER_RUNTIME_REPORT_20260626.md",
    "PHASE8_MARKETPLACE_SANDBOX_RUNTIME_REPORT_20260626.md",
    "PHASE9_FEDERATED_AGENT_CONSENSUS_RUNTIME_REPORT_20260626.md",
    "PHASE10_RELIABILITY_LOAD_CHAOS_RECOVERY_REPORT_20260626.md",
    "PHASE11_MOBILE_OFFLINE_SYNC_RUNTIME_REPORT_20260626.md",
    "PHASE12_FINAL_PRODUCTION_GATES_REPORT_20260626.md",
    "PHASE13_PRODUCTION_OBSERVABILITY_DASHBOARDS_REPORT_20260626.md",
    "PHASE14_RELEASE_PACKAGING_DEPLOYMENT_READINESS_REPORT_20260626.md",
    "PHASE15_DEPLOYMENT_AUTOMATION_HELM_GITOPS_REPORT_20260626.md",
    "PHASE16_CI_CD_QUALITY_GATES_SUPPLY_CHAIN_REPORT_20260626.md",
    "PHASE17_RUNTIME_BOOTSTRAP_ENV_DOCTOR_REPORT_20260626.md",
    "PHASE18_URGENT_PRODUCTION_RUNTIME_FIXES_REPORT_20260626.md",
    "PHASE19_PRODUCTION_GAP_CLOSURE_MIGRATIONS_EXEC_BITS_REPORT_20260626.md",
    "PHASE20_RUNTIME_WORKER_SIDE_EFFECTS_REPORT_20260626.md",
    "PHASE21_PRODUCTION_CERTIFICATION_READINESS_REPORT_20260626.md",
    "PHASE22_RLS_WITH_CHECK_TENANT_SESSION_HARDENING_REPORT_20260626.md",
]


def is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.name in EXCLUDE_SUFFIXES:
        return True
    if any(path.name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
        return True
    return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _tracked_files(root: Path) -> list[Path]:
    """ملفّات git المُتعقَّبة فقط — حتّى تكون البصمة حتميّة بصرف النظر عن ملفّات
    محلّيّة مُتجاهَلة (.env/.ruff_cache…) قد يلتقطها rglob فتُفسد التحقّق في CI.
    تراجُع آمن إلى rglob إن تعذّر git (أرشيف بلا مستودع)."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        rels = [p for p in out.split("\0") if p]
        if rels:
            return [root / r for r in rels]
    except (OSError, subprocess.CalledProcessError):
        pass
    return [p for p in root.rglob("*") if p.is_file()]


def collect_files(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for file_path in sorted(_tracked_files(root)):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(root)
        if is_excluded(rel):
            continue
        # Do not include generated release checksum files in their own checksum set.
        if str(rel) in {
            "release/FILE_CHECKSUMS.sha256",
            "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
            "release/SBOM_MINIMAL.json",
        }:
            continue
        rows.append(
            {
                "path": str(rel),
                "size_bytes": file_path.stat().st_size,
                "sha256": sha256_file(file_path),
            }
        )
    return rows


def infer_components(files: list[dict[str, object]]) -> dict[str, object]:
    prefixes = [
        "services/",
        "shared/",
        "frontend/",
        "mobile/",
        "grafana/",
        "prometheus/",
        "migrations/",
        "scripts/",
        "tests/",
    ]
    counts = {prefix.rstrip("/"): 0 for prefix in prefixes}
    for row in files:
        p = str(row["path"])
        for prefix in prefixes:
            if p.startswith(prefix):
                counts[prefix.rstrip("/")] += 1
    return {"component_file_counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--release-dir", default="release", help="release output directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    release_dir = root / args.release_dir
    release_dir.mkdir(parents=True, exist_ok=True)

    missing = [p for p in REQUIRED_FILES + REQUIRED_REPORTS if not (root / p).exists()]
    files = collect_files(root)
    version = (
        (root / "VERSION").read_text(encoding="utf-8").strip()
        if (root / "VERSION").exists()
        else "UNKNOWN"
    )

    checksum_lines = [f"{row['sha256']}  {row['path']}" for row in files]
    (release_dir / "FILE_CHECKSUMS.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )

    manifest = {
        "release_name": version,
        # ختم مشتقّ من المصدر لا من ساعة الحائط — `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`.
        # `datetime.now()` كان يكتب قيمة جديدة في كلّ تشغيل، فإعادة توليد على فرع لم
        # يتغيّر حمولته تُنتج فرقاً سطريّاً مضموناً، وفرعان متوازيان يتعارضان حتماً.
        "generated_at": generated_at_utc(cwd=root),
        # `source_root: root.name` حُذِف: **صفر قارئ** في المستودع كلّه (المُنتِج وحده)،
        # وكان يطبع **اسم مجلّد السحب** فيختم الآلة في مصنوعة إصدار. قِيس فعليّاً:
        # التوليد داخل شجرة عمل اسمها `wt768` كتب `"source_root": "wt768"`. نفس صنف
        # `RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01`. حقلٌ بلا قارئ يسرّب البيئة
        # ليس provenance بل ضجيج يتعارض.
        "file_count": len(files),
        "total_size_bytes": sum(int(row["size_bytes"]) for row in files),
        "missing_required_assets": missing,
        "required_files": REQUIRED_FILES,
        "required_reports": REQUIRED_REPORTS,
        "checksums_file": "release/FILE_CHECKSUMS.sha256",
        "components": infer_components(files),
        "deployment_gates": [
            "scripts/production_validation_gate.sh",
            "scripts/security_audit.sh",
            "scripts/observability/validate_observability_assets.py",
            "scripts/release/validate_release_package.py",
            "scripts/ci/validate_ci_gates.py",
            "scripts/ci/github_actions_policy_guard.py",
            "scripts/ci/release_attestation_guard.py",
            "scripts/ci/secret_history_scan_guard.py",
            "scripts/ci/github_actions_policy_guard.py",
            "scripts/ci/frontend_reproducibility_guard.py",
            "scripts/ci/local_test_dependency_preflight.py",
            "scripts/ci/local_quality_gate.sh",
            "scripts/ci/raster_quality_gate.sh",
            "scripts/runtime/env_doctor.py",
            "scripts/runtime/runtime_doctor.sh",
            "scripts/migrations/validate_migration_manifest.py",
            "migrations/v113_phase_runtime_workers_jobs.sql",
            "services/sahool-platform/api/phase_runtime_workers.py",
            "shared/runtime_worker_contracts.py",
            "scripts/workers/run_phase_runtime_worker.sh",
        ],
        "runtime_validation_sequence": [
            "docker compose -f docker-compose.v9.yml config",
            "bash scripts/production_validation_gate.sh",
            "bash scripts/check_gateway_routes.sh",
            "BASE_URL=http://localhost bash scripts/runtime_smoke.sh",
            "SAHOOL_JWT=<jwt> TENANT_ID=<tenant> FIELD_ID=<field> BASE_URL=http://localhost bash scripts/e2e/e2e_field_imagery_ai.sh",
            "bash scripts/load/run_load_tests.sh",
            "bash scripts/chaos/run_chaos_tests.sh",
            "bash scripts/recovery/recovery_smoke.sh",
        ],
    }
    (release_dir / "SAHOOL_RELEASE_MANIFEST_20260626.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    sbom = {
        "bomFormat": "CycloneDX-lite",
        "specVersion": "informal-source-inventory",
        "metadata": {"component": {"name": "sahool", "version": version}},
        "components": [
            {
                "name": row["path"],
                "type": "file",
                "hashes": [{"alg": "SHA-256", "content": row["sha256"]}],
            }
            for row in files
            if str(row["path"]).startswith(
                ("services/", "shared/", "frontend/", "mobile/", "docker-compose", "migrations/")
            )
        ],
    }
    (release_dir / "SBOM_MINIMAL.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migration_manifest_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/migrations/validate_migration_manifest.py", "--root", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "migration manifest validation passed" in result.stdout


def test_legacy_migration_runner_is_manifest_driven() -> None:
    migrate = (ROOT / "scripts_v9/migrate.py").read_text(encoding="utf-8")
    sql = (ROOT / "scripts_v9/run_migrations.sql").read_text(encoding="utf-8")
    manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    assert "MANIFEST.txt" in migrate
    assert "manifest_order" in migrate
    assert "MANIFEST.txt" in sql
    for name in [
        "v106_phase9_10_runtime_strengthening.sql",
        "v108_phase10_feature_store_model_registry_runtime.sql",
        "v113_phase_runtime_workers_jobs.sql",
    ]:
        assert name in manifest
        assert f"migrations/{name}" in sql


def test_no_duplicate_numeric_migration_prefixes_except_v9_family() -> None:
    import re
    from collections import defaultdict

    grouped: dict[str, list[str]] = defaultdict(list)
    for path in (ROOT / "migrations").glob("*.sql"):
        if path.name.endswith(".down.sql"):
            continue
        match = re.match(r"^(v\d+)(?:_|$)", path.name)
        if match:
            grouped[match.group(1)].append(path.name)
    duplicates = {k: v for k, v in grouped.items() if len(v) > 1 and k != "v9"}
    assert duplicates == {}


def test_runtime_activation_migrations_were_renumbered_out_of_duplicate_range() -> None:
    manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    for name in [
        "v114_cloud_native_gis_best_practices.sql",
        "v115_precision_agriculture_phase6.sql",
        "v116_enterprise_gis_phase7.sql",
        "v117_global_scale_phase8.sql",
        "v118_phase9_autonomous_farm_os.sql",
        "v119_phase10_continuous_learning.sql",
        "v120_phase11_federated_agents.sql",
        "v121_marketplace_ecosystem.sql",
    ]:
        assert (ROOT / "migrations" / name).exists(), name
        assert name in manifest

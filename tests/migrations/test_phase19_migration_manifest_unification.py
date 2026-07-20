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


def test_no_cross_system_migration_id_collision_between_alembic_and_migrations() -> None:
    """MIGRATE-ID-COLLISION مُغلَق: نظاما الهجرة يملكان فضاءَي ترقيم **منفصلَين**.

    التصادم القديم: ``alembic/versions/v101_field_runtime_cohesion.sql`` و
    ``v105_marketplace_ecosystem.sql`` أعادا استعمال أرقام vNNN المملوكة لـ``migrations/``
    (v101=farm_budget_costing · v105=enterprise_imagery؛ marketplace canonical = v121) ⇒
    «نفس الرقم، ملفّان مختلفان لكلّ نظام». الملفّان كانا ميّتَين (خارج سلسلة مراجعات alembic
    0001→0002، لا يطبّقهما أيّ runner، صفر استعمال لجداولهما) فأُزيلا. الحارس يمنع الانحدار:
      • ``alembic/versions/`` = مراجعات alembic الأصليّة ``NNNN_*.py`` حصراً — لا ``vNNN_*.sql``.
      • ``migrations/`` = هجرات ``vNNN_*.sql`` حصراً — لا مراجعات alembic ``NNNN_*.py``.
    """
    stray_sql_in_alembic = sorted(p.name for p in (ROOT / "alembic/versions").glob("v*.sql"))
    assert stray_sql_in_alembic == [], (
        "alembic/versions/ يجب ألّا يحوي ملفّات vNNN_*.sql (فضاء migrations/): "
        f"{stray_sql_in_alembic} — يعيد تصادم معرّفات الهجرة عبر النظامين."
    )
    stray_alembic_in_migrations = sorted(
        p.name for p in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.py")
    )
    assert stray_alembic_in_migrations == [], (
        f"migrations/ يجب ألّا يحوي مراجعات alembic NNNN_*.py: {stray_alembic_in_migrations}"
    )


def test_alembic_vnnn_collision_guard_negative_proof(tmp_path) -> None:
    """برهان سلبيّ: زرع ملفّ ``vNNN_*.sql`` اصطناعيّ في مجلّد alembic-شبيه يقلب الحارس أحمر.

    يمنع أن يمرّ الحارس **فراغاً** (vacuously): لو كان المنطق معطوباً لَما التقط الزومبيّ.
    """
    fake_versions = tmp_path / "alembic" / "versions"
    fake_versions.mkdir(parents=True)
    (fake_versions / "0001_baseline.py").write_text("revision='0001_baseline'\n", encoding="utf-8")
    (fake_versions / "v101_field_runtime_cohesion.sql").write_text(
        "CREATE TABLE zombie(id int);\n", encoding="utf-8"
    )
    stray = sorted(p.name for p in fake_versions.glob("v*.sql"))
    assert stray == ["v101_field_runtime_cohesion.sql"], (
        "منطق الحارس يجب أن يلتقط ملفّ vNNN_*.sql الاصطناعيّ (وإلّا الحارس يمرّ فراغاً)"
    )

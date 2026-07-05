"""حارس: أمر مهمّة ترحيل helm يشير إلى مُشغّل موجود (تدقيق 2026-07-05).

كان `python -m api.migrations.run` يشير لوحدة غير موجودة ⇒ مهمّة الترحيل في k8s
تفشل عند الإقلاع. المُشغّل الفعليّ scripts_v9/migrate.py (backed by MANIFEST). ساكن
بحت (يقرأ values.yaml) — يعمل بلا k8s ويمنع انحدار أمر ميّت.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
VALUES = REPO / "helm" / "sahool" / "values.yaml"


def test_helm_migration_command_points_to_existing_runner():
    import yaml

    cfg = yaml.safe_load(VALUES.read_text(encoding="utf-8"))
    cmd = cfg["jobs"]["migration"]["command"]
    assert isinstance(cmd, list) and cmd, "أمر الترحيل يجب أن يكون قائمة غير فارغة"
    # يجب ألّا يشير إلى الوحدة الميّتة القديمة.
    joined = " ".join(cmd)
    assert "api.migrations.run" not in joined, "أمر helm يشير لوحدة غير موجودة (api.migrations.run)"
    # يجب أن يشير إلى ملفّ/وحدة موجودة فعلاً في المستودع.
    script_ref = next(
        (c for c in cmd if c.endswith(".py") or c.startswith("api.") or c.startswith("scripts")),
        None,
    )
    assert script_ref, f"أمر الترحيل بلا مرجع سكربت واضح: {cmd}"
    if script_ref.endswith(".py"):
        assert (REPO / script_ref).is_file(), f"سكربت الترحيل غير موجود: {script_ref}"


def test_migrate_runner_accepts_jobs_database_url():
    """migrate.py يقرأ JOBS_DATABASE_URL (helm يمرّره باسمه) كي يعمل مسار النشر."""
    src = (REPO / "scripts_v9" / "migrate.py").read_text(encoding="utf-8")
    assert "JOBS_DATABASE_URL" in src, "migrate.py يجب أن يقبل JOBS_DATABASE_URL (بيئة helm)"

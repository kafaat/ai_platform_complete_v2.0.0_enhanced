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
    script_refs = [
        c
        for c in cmd
        if c.endswith((".py", ".sh")) or c.startswith("api.") or c.startswith("scripts")
    ]
    assert script_refs, f"أمر الترحيل بلا مرجع سكربت واضح: {cmd}"
    # تدقيق 2026-11-01 (I1): المهمّة تعمل الآن على صورة المهاجر (deploy/railway/Dockerfile.migrate)
    # بمساراتٍ مطلقة داخل الصورة؛ كلٌّ منها يجب أن يُطابِق ملفّاً في المستودع: /migrations/* من
    # migrations/ (COPY في Dockerfile.migrate)، و/opt/sahool-migrate/* من helm/sahool/files/
    # (ConfigMap). المرجع الذي لا يُطابِق ملفّاً قائماً يبقى أمراً ميّتاً كما كان api.migrations.run.
    image_roots = {"/migrations/": "migrations/", "/opt/sahool-migrate/": "helm/sahool/files/"}
    for ref in script_refs:
        if ref.endswith(".py") and not ref.startswith("/"):
            assert (REPO / ref).is_file(), f"سكربت الترحيل غير موجود: {ref}"
        elif ref.startswith("/"):
            mapped = next(
                (
                    repo + ref[len(img) :]
                    for img, repo in image_roots.items()
                    if ref.startswith(img)
                ),
                None,
            )
            assert mapped, f"مسار مطلق خارج جذور الصورة المعروفة: {ref}"
            assert (REPO / mapped).is_file(), (
                f"مرجع الترحيل لا يطابق ملفّاً في المستودع: {ref} → {mapped}"
            )


def test_migrate_runner_accepts_jobs_database_url():
    """migrate.py يقرأ JOBS_DATABASE_URL (helm يمرّره باسمه) كي يعمل مسار النشر."""
    src = (REPO / "scripts_v9" / "migrate.py").read_text(encoding="utf-8")
    assert "JOBS_DATABASE_URL" in src, "migrate.py يجب أن يقبل JOBS_DATABASE_URL (بيئة helm)"

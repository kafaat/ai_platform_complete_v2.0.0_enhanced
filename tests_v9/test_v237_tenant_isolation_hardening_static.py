"""حارس ساكن v237 (تدقيق 2026-11-01: T1/T2/T3/T7/T8/T9) — عقد الملفّ بلا قاعدة.

البرهان الحيّ (التسرّبات قبل/بعد على PostgreSQL مبنيّة من MANIFEST) في
``test_v237_tenant_isolation_live_pg.py``. هنا ما يجب ألّا ينجرف نصّيّاً:

* مُسجَّل في المُشغّلَين **قبل** v206 (v206 يبقى آخر مدخل).
* ذرّيّ (BEGIN/COMMIT) ويحمل تأكيدات الكتالوج الستّة.
* ينتقي السياسات **بالشكل** لا بالاسم (الخطأ الذي فوّت به v206 عشرين سياسة).
* لا VALIDATE CONSTRAINT أعمى (عرف v127/v130) — والقيود الجديدة متتبَّعة في سكربت التقرير.
* لملفّ التراجع لقطةٌ يستعيد منها (COMMENT ON POLICY) ويعيد تشغيل v206.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MIG = _ROOT / "migrations" / "v237_tenant_isolation_hardening.sql"
_DOWN = _ROOT / "migrations" / "v237_tenant_isolation_hardening.down.sql"
_MANIFEST = _ROOT / "migrations" / "MANIFEST.txt"
_RUNNER = _ROOT / "scripts_v9" / "run_migrations.sql"
_REPORT = _ROOT / "scripts" / "migrations" / "report_not_valid_constraint_violations.py"


def _code(path: Path) -> str:
    return "\n".join(
        line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
    )


def _entries() -> list[str]:
    return [
        ln.strip()
        for ln in _MANIFEST.read_text(encoding="utf-8").splitlines()
        if ln.strip().endswith(".sql") and not ln.lstrip().startswith("#")
    ]


def test_registered_after_v236_and_before_v206_in_both_runners() -> None:
    entries = _entries()
    i = entries.index(_MIG.name)
    assert entries[i - 1] == "v236_raster_follow_up_requests.sql"
    assert entries[-1] == "v206_rls_final_hardening.sql"
    runner = _RUNNER.read_text(encoding="utf-8")
    assert runner.index(f"migrations/{_MIG.name}") < runner.index(
        "migrations/v206_rls_final_hardening.sql"
    )


def test_atomic_and_carries_every_catalog_assertion() -> None:
    code = _code(_MIG)
    assert code.lstrip().startswith("BEGIN;") and code.rstrip().endswith("COMMIT;")
    for tag in ("A1", "A2", "A3", "A4", "A5", "A6"):
        assert f"v237 {tag}:" in code, f"catalog assertion {tag} missing"
    assert code.count("RAISE EXCEPTION") >= 7


def test_policies_selected_by_shape_not_by_name() -> None:
    code = _code(_MIG)
    # v206 انتقى «policyname = 'tenant_isolation'» ففاته كلّ ما سُمّي بغيره (webhooks…).
    assert not re.search(r"policyname\s*=\s*'", code)
    assert "permissive = 'PERMISSIVE'" in code
    assert "security_invoker = true" in code
    assert "sahool_effective_tenant_id()" in code


def test_definer_revokes_and_no_blind_validate() -> None:
    code = _code(_MIG)
    for fn in (
        "claim_submissions_for_projection(integer,integer)",
        "complete_submission_projection(bigint,text,text)",
        "resolve_ingest_source(text)",
    ):
        assert f"public.{fn}" in code
    assert "REVOKE EXECUTE ON FUNCTION %s FROM sahool_app" in code
    assert "NOT VALID" in code
    assert "VALIDATE CONSTRAINT" not in code.upper()


def test_report_script_tracks_the_new_not_valid_constraints() -> None:
    report = _REPORT.read_text(encoding="utf-8")
    assert _MIG.name in report
    assert "_tenant_nonempty" in report and "btrim(tenant_id) <> ''" in report


def test_down_script_restores_from_snapshot_and_reruns_v206() -> None:
    up, down = _code(_MIG), _DOWN.read_text(encoding="utf-8")
    assert "'v237-prev:'" in up and "COMMENT ON POLICY" in up
    assert "LIKE 'v237-prev:%'" in down
    assert down.rstrip().endswith(r"\ir v206_rls_final_hardening.sql")
    # لا يعيد تسرّب T3: EXECUTE لم تمنحه هجرة.
    assert "GRANT EXECUTE" not in _code(_DOWN)

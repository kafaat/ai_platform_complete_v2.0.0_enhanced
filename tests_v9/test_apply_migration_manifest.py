"""المُشغّل القانونيّ لبيان الهجرات — ملكيّةُ المجرى وعدديّةُ التطبيق.

`MIGRATION-STDIN-OWNERSHIP-01` — العطل مقيسٌ في 32285597465 لا مُتخيَّل: التعداد
كان من **مجرى حيّ**، وغلافُ العميل المُحوَّى يُشغّل `docker run -i` فيستنزفه.
فطُبِّقت `init_v8.sql` وحدها ثمّ EOF: ``هجرات مُطبَّقة: 1 من 226``. وتَبِعه في
Integration انفجارٌ ثانويّ (57 فشلاً · 23 خطأً) كلّه ``relation ... does not
exist`` — أعراضٌ لا تشخيص.

والمقيس هنا ثلاثة عقودٍ مستقلّة:
  ① **ملكيّة المجرى**: عميلٌ يقرأ stdin عمداً لا يُنقِص عنصراً واحداً من البيان.
  ② **بوّابة العدديّة**: نقصٌ في المُطبَّق يحجب **قبل** أن يبدأ أيّ اختبار.
  ③ **الفحص قبل اللمس**: اسمٌ في البيان بلا ملفّ يفشل قبل أن تُمَسّ القاعدة، فلا
     تُترَك قاعدةٌ نصفَ مُهاجَرة.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "ci" / "apply_migration_manifest.sh"
CI = ROOT / ".github/workflows/ci.yml"


def _workspace(tmp_path: Path, names: list[str], *, greedy_psql: bool, create: bool = True):
    """شجرةٌ مصغّرة ببيانٍ وملفّاته، و`psql` مزيّف يقرأ stdin **عمداً**."""
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations/MANIFEST.txt").write_text(
        "# تعليقٌ يُتجاهَل\n\n" + "\n".join(names) + "\n", encoding="utf-8"
    )
    if create:
        for n in names:
            (tmp_path / "migrations" / n).write_text("select 1;\n", encoding="utf-8")
    log = tmp_path / "applied.log"
    drain = "cat >/dev/null || true\n" if greedy_psql else ""
    psql = tmp_path / "psql"
    psql.write_text(
        "#!/usr/bin/env bash\n"
        'for a in "$@"; do case "$a" in migrations/*) '
        f'echo "$a" >> "{log}";; esac; done\n' + drain + "exit 0\n",
        encoding="utf-8",
    )
    psql.chmod(0o755)
    return log


def _run(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUNNER), "--port", "5433", "--user", "u", "--db", "d", *extra],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
    )


def test_a_client_that_reads_stdin_cannot_truncate_the_manifest(tmp_path):
    """العطل المؤسِّس: عميلٌ نهِمٌ للمجرى كان يُنهي التعداد بعد أوّل ملفّ."""
    names = [f"v{i:03d}.sql" for i in range(1, 13)]
    log = _workspace(tmp_path, names, greedy_psql=True)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    applied = log.read_text(encoding="utf-8").split()
    assert applied == [f"migrations/{n}" for n in names], (
        f"طُبِّق {len(applied)} من {len(names)} — المجرى استُنزِف"
    )
    assert f"applied={len(names)} expected={len(names)}" in result.stdout


def test_the_cardinality_gate_blocks_before_any_test_can_start(tmp_path):
    """نقصُ التطبيق يحجب — ولا يُترَك لاختباراتٍ لاحقة أن تُبلِغ عنه أعراضاً."""
    names = [f"v{i:03d}.sql" for i in range(1, 6)]
    _workspace(tmp_path, names, greedy_psql=False)
    # `psql` يفشل عند الثالث: التطبيق يتوقّف والعدديّة لا تكتمل.
    (tmp_path / "psql").write_text(
        '#!/usr/bin/env bash\ncase "$*" in *v003.sql*) echo "boom" >&2; exit 1;; esac\nexit 0\n',
        encoding="utf-8",
    )
    (tmp_path / "psql").chmod(0o755)
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "migration[2/5]" in result.stdout, result.stdout


def test_a_manifest_entry_without_a_file_fails_before_touching_the_database(tmp_path):
    """وإلّا تُركت قاعدةٌ نصفَ مُهاجَرة، وهي أسوأ من قاعدةٍ لم تُلمَس."""
    names = ["v001.sql", "ghost.sql"]
    log = _workspace(tmp_path, names, greedy_psql=False, create=False)
    (tmp_path / "migrations/v001.sql").write_text("select 1;\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "MIGRATION_FILE_MISSING" in result.stdout + result.stderr
    assert not log.exists(), "لُمِست القاعدة قبل اكتمال الفحص"


def test_an_empty_or_missing_manifest_fails_closed(tmp_path):
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations/MANIFEST.txt").write_text("# لا شيء\n", encoding="utf-8")
    (tmp_path / "psql").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (tmp_path / "psql").chmod(0o755)
    assert "MIGRATION_MANIFEST_EMPTY" in _run(tmp_path).stdout + _run(tmp_path).stderr


def test_both_jobs_use_the_one_canonical_runner_and_not_a_copied_loop():
    """تعريفٌ واحد لعبارة «طُبِّق البيان» — والانحرافُ كان مقيساً: Live PG تحمل
    عدّاداً وIntegration لا تحمله، فأعطت **أخضرَ كاذباً** لقاعدةٍ ناقصة 225 هجرة.
    """
    ci = CI.read_text(encoding="utf-8")
    assert ci.count("apply_migration_manifest.sh") == 2
    # ولا يبقى **أيّ** مُعدِّدٍ آخر للبيان في الشجرة. النسخة الثالثة كانت في
    # `scripts/irr_f01/upgrade_gate_u1.sh` وأسقطت 32290853228 بعد أن ظننّا العطل
    # مُغلَقاً — لأنّ الفحص كان على `ci.yml` وحدها.
    offenders = []
    for path in sorted(ROOT.glob("scripts/**/*.sh")) + sorted(ROOT.glob(".github/workflows/*.yml")):
        if path.name == "apply_migration_manifest.sh":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "MANIFEST" in line and "done <" in line:
                offenders.append(f"{path.relative_to(ROOT)}: {line.strip()[:70]}")
    assert not offenders, offenders


def test_the_bounded_variant_stops_before_the_named_prefix(tmp_path):
    """بوّابة الترقية تحتاج تطبيقاً محدوداً — وهي الحاجة التي بُنيت لأجلها نسختها."""
    names = ["v190.sql", "v194.sql", "v195_upgrade.sql", "v196.sql"]
    log = _workspace(tmp_path, names, greedy_psql=True)
    result = subprocess.run(
        [
            "bash",
            str(RUNNER),
            "--port",
            "5433",
            "--user",
            "u",
            "--db",
            "d",
            "--stop-before",
            "v195_*",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert log.read_text(encoding="utf-8").split() == [
        "migrations/v190.sql",
        "migrations/v194.sql",
    ], "الحدّ لم يقف عند النمط المُسمّى"
    assert "applied=2 expected=2" in result.stdout


# ── `EVIDENCE-PRIMARY-CAUSE-PROPAGATION-01` ──────────────────────────────────
# رفعه المالك بقياسٍ من الحزمة المرفوعة: `live_pg_evidence.json` قال
# `JUNIT_REPORT_MISSING` و`live_pg_role_closure.json` قال
# `RESTRICTED_ROLE_NOT_FOUND` — وكلاهما **عَرَضٌ تالٍ** لعطلٍ سببيّ أعلى
# (`applied=1/226`). ونسبةُ الفشل إلى العَرَض تُفسِد سلسلة النَّسَب في تقرير
# الاعتماد: يصير أيّ عطلٍ سابق قابلاً للنسبة إلى سببٍ ثابت لا علاقة له بالمقيس.


def test_the_first_causal_failure_is_inherited_not_replaced_by_a_symptom():
    ci = CI.read_text(encoding="utf-8")
    # عطلُ الهجرات يترك فُتاتاً سببيّاً
    assert "MIGRATION_MANIFEST_APPLY_FAILED" in ci
    assert "live_pg_primary_cause.txt" in ci
    # وبناءُ المواضيع يقرؤه **أوّلاً** قبل أيّ اشتقاقٍ من حالة العالم
    body = ci[ci.index("HARNESS_INVALID") - 2000 : ci.index("HARNESS_INVALID")]
    inherit = body.index("live_pg_primary_cause.txt")
    derive = body.index("command -v psql")
    assert inherit < derive, "الاشتقاق يسبق الوراثة — العَرَض يغلب السبب"


def test_semantic_proofs_do_not_run_when_migrations_did_not_complete():
    """وإلّا كتبت `FAIL` عن قياسٍ لم يقع — والصواب أنّها **لم تُنفَّذ**."""
    ci = CI.read_text(encoding="utf-8")
    assert ci.count("steps.live_pg_migrations.outcome == 'success'") == 2, (
        "شهادةُ الدور وعقدُ الوظيفة يجب أن يشترطا اكتمال الهجرات"
    )


def test_the_bound_accepts_an_alternation_of_prefixes(tmp_path):
    """العقد القائم يُصرّح بالبادئتين معاً (`v195_*|v196_*`).

    اختزالُه في واحدةٍ يعتمد ضمناً على ترتيب البيان، وقد أمسك ذلك حارسٌ قائم:
    `tests/irrigation/test_irr_f01_certification_ci_contract.py` يفرض بقاء النصّ
    صريحاً — فاحمرّ على اختزالي في 32292741829.
    """
    names = ["v190.sql", "v196_late.sql", "v195_upgrade.sql"]
    log = _workspace(tmp_path, names, greedy_psql=True)
    result = subprocess.run(
        [
            "bash",
            str(RUNNER),
            "--port",
            "5433",
            "--user",
            "u",
            "--db",
            "d",
            "--stop-before",
            "v195_*|v196_*",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # يقف عند `v196_late.sql` رغم أنّها ليست البادئة الأولى في التناوب.
    assert log.read_text(encoding="utf-8").split() == ["migrations/v190.sql"]

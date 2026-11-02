"""مهمّة الهجرة في helm تشغّل ما تحويه صورتها فعلاً (I1، تدقيق 2026-11-01).

كانت ``jobs.migration`` تشغّل ``python scripts_v9/migrate.py up`` في صورة المنصّة، وتلك الصورة
لا تنسخ إلّا ``services/sahool-platform/`` ولا تحمل ``psql`` ⇒ يفشل خطّاف pre-install في كلّ
``helm install``. الآن: صورة مُهاجر Railway نفسها (``deploy/railway/Dockerfile.migrate``) ومُشغّلها
نفسه (``/migrations/apply_in_compose.sh``) خلف مُحوِّلٍ رفيع يشتقّ PG* من ``JOBS_DATABASE_URL``،
وإذن التطبيق ``SAHOOL_MIGRATE_APPLY`` افتراضيّه "0" كما في Railway.

helm غير مُتاح في CI، فالفحص ساكن: القيم والقالب يُقرآن، والمُحوِّل يُنفَّذ فعلاً بـbash.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"
TEMPLATE = CHART / "templates" / "migration-job.yaml"
WRAPPER = CHART / "files" / "migration-dsn-env.sh"
VALIDATOR = ROOT / "scripts" / "deploy" / "validate_helm_readiness.py"


def _validator():
    spec = importlib.util.spec_from_file_location("validate_helm_readiness", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _merged(env: str) -> dict:
    v = _validator()
    return v.deep_merge(
        v.load_yaml(CHART / "values.yaml"), v.load_yaml(CHART / f"values-{env}.yaml")
    )


@pytest.mark.parametrize("env", ["staging", "production"])
def test_the_migration_job_runs_only_what_its_image_contains(env):
    assert _validator().migration_job_errors(_merged(env)) == []


def test_the_old_platform_image_command_is_rejected():
    """تكذيب الحارس على الشكل الذي كسر كلّ helm install."""
    values = _merged("production")
    values["jobs"]["migration"].update(
        image="sahool/platform:2026.06.26-rc.15",
        sourceDockerfile="services/sahool-platform/Dockerfile",
        command=["python", "scripts_v9/migrate.py", "up"],
    )
    errors = _validator().migration_job_errors(values)
    assert any("scripts_v9/migrate.py" in e for e in errors), errors


def test_a_baked_apply_permission_is_rejected():
    values = _merged("production")
    values["jobs"]["migration"]["apply"] = True
    errors = _validator().migration_job_errors(values)
    assert any("apply must be false" in e for e in errors), errors


def test_the_job_uses_the_railway_migrator_image_and_entrypoint():
    job = _merged("production")["jobs"]["migration"]
    dockerfile = (ROOT / job["sourceDockerfile"]).read_text(encoding="utf-8")
    entry = re.search(r"^ENTRYPOINT\s+(\[.*\])\s*$", dockerfile, re.M)
    assert entry, "Dockerfile.migrate بلا ENTRYPOINT"
    railway_runner = yaml.safe_load(entry.group(1))[-1]
    assert job["command"][-1] == railway_runner == "/migrations/apply_in_compose.sh"
    assert job["apply"] is False


def test_the_template_wires_the_apply_gate_and_the_wrapper_mount():
    text = TEMPLATE.read_text(encoding="utf-8")
    job = _merged("production")["jobs"]["migration"]
    assert "- name: SAHOOL_MIGRATE_APPLY" in text
    assert 'ternary "1" "0" (eq (toString .Values.jobs.migration.apply) "true")' in text
    # كلمات مرور الأدوار تُحقَن فقط تحت شرط apply.
    gate = text.index('{{- if eq (toString .Values.jobs.migration.apply) "true" }}')
    assert gate < text.index("applySecretEnv")
    assert f'.Files.Get "files/{WRAPPER.name}"' in text
    mount_dir = job["command"][1].rsplit("/", 1)[0]
    assert f"mountPath: {mount_dir}" in text
    assert "mountPath: /tmp" in text, "probe_schema_state.sh يكتب بـmktemp والجذر للقراءة فقط"


_STUB = 'printf "%s=%s\\n" HOST "$PGHOST" PORT "$PGPORT" USER "$PGUSER" PW "${PGPASSWORD-<unset>}" DB "$PGDATABASE" SSL "${PGSSLMODE-<unset>}" ROOT "${PGSSLROOTCERT-<unset>}" APPLY "${SAHOOL_MIGRATE_APPLY-<unset>}" RAW "${JOBS_DATABASE_URL-<unset>}"\n'


def _run(tmp_path: Path, dsn: str | None, apply: str = "0"):
    stub = tmp_path / "runner.sh"
    stub.write_text(_STUB, encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "SAHOOL_MIGRATE_APPLY": apply}
    if dsn is not None:
        env["JOBS_DATABASE_URL"] = dsn
    return subprocess.run(
        ["bash", str(WRAPPER), str(stub)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )


def _parse(stdout: str) -> dict:
    return dict(line.split("=", 1) for line in stdout.splitlines())


def test_the_wrapper_derives_pg_env_and_passes_the_apply_gate_through(tmp_path):
    dsn = (
        "postgresql://sahool_user:p%40ss%2Fw%5Cd@db.internal:6543/sahool"
        "?sslmode=verify-full&sslrootcert=/etc/ca.pem"
    )
    result = _run(tmp_path, dsn)
    assert result.returncode == 0, result.stderr
    got = _parse(result.stdout)
    assert got == {
        "HOST": "db.internal",
        "PORT": "6543",
        "USER": "sahool_user",
        "PW": "p@ss/w\\d",
        "DB": "sahool",
        "SSL": "verify-full",
        "ROOT": "/etc/ca.pem",
        "APPLY": "0",
        "RAW": "<unset>",
    }


def test_the_wrapper_defaults_the_port_and_keeps_apply_one_only_when_given(tmp_path):
    result = _run(tmp_path, "postgres://u@h/d", apply="1")
    assert result.returncode == 0, result.stderr
    got = _parse(result.stdout)
    assert (got["PORT"], got["PW"], got["APPLY"]) == ("5432", "<unset>", "1")


@pytest.mark.parametrize(
    ("dsn", "reason"),
    [
        (None, "dsn_missing"),
        ("mysql://u:hunter2x@h/d", "dsn_unparseable"),
        ("postgresql://u:hunter2x@h:5432", "dsn_unparseable"),
        ("postgresql://u:hunter2x@h/d?sslmode=require&gssencmode=x", "dsn_unsupported_param"),
    ],
)
def test_the_wrapper_fails_closed_before_any_connection(tmp_path, dsn, reason):
    result = _run(tmp_path, dsn)
    assert result.returncode == 2
    assert f"MIGRATIONS_NOT_APPLIED reason={reason}" in result.stderr
    assert result.stdout == "", "المُشغّل نُفِّذ رغم DSN مرفوض"
    assert "hunter2x" not in result.stdout + result.stderr

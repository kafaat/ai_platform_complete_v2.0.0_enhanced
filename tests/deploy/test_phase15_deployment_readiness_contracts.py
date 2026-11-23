import json
import shlex
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_helm_chart_assets_exist():
    chart = ROOT / "helm" / "sahool"
    required = [
        "Chart.yaml",
        "values.yaml",
        "values-production.yaml",
        "templates/deployments.yaml",
        "templates/services.yaml",
        "templates/ingress.yaml",
        "templates/networkpolicy.yaml",
        "templates/migration-job.yaml",
    ]
    for rel in required:
        assert (chart / rel).exists(), rel


def test_production_values_are_not_single_replica_or_latest():
    base = yaml.safe_load((ROOT / "helm/sahool/values.yaml").read_text(encoding="utf-8"))
    prod = yaml.safe_load((ROOT / "helm/sahool/values-production.yaml").read_text(encoding="utf-8"))
    workloads = base["workloads"]
    for name, override in prod.get("workloads", {}).items():
        merged = {**workloads[name], **override}
        if name == "sahool-knowledge-graph":
            # SQLite has one persistent owner; scaling requires a storage migration.
            assert merged["replicas"] == 1
            assert merged["env"]["KG_SQLITE_PATH"] == "/data/kg.sqlite"
            assert merged["persistence"]["mountPath"] == "/data"
            assert merged["persistence"]["accessMode"] == "ReadWriteOnce"
        else:
            assert merged["replicas"] >= 2, name
        assert not merged["image"].endswith(":latest"), name
    assert prod["global"]["environment"] == "production"


def test_templates_have_runtime_hardening_contracts():
    text = (ROOT / "helm/sahool/templates/deployments.yaml").read_text(encoding="utf-8")
    for expected in [
        "readinessProbe",
        "livenessProbe",
        "runAsNonRoot: true",
        "allowPrivilegeEscalation: false",
        "readOnlyRootFilesystem: true",
        "prometheus.io/scrape",
    ]:
        assert expected in text


def test_migration_job_uses_jobs_database_secret_only():
    text = (ROOT / "helm/sahool/templates/migration-job.yaml").read_text(encoding="utf-8")
    assert "JOBS_DATABASE_URL" in text
    assert "DATABASE_URL" not in text.replace("JOBS_DATABASE_URL", "")
    assert "helm.sh/hook: pre-install,pre-upgrade" in text


def test_deployment_readiness_validator_passes_for_production():
    result = subprocess.run(
        ["python", "scripts/deploy/validate_helm_readiness.py", "--env", "production"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_railway_auth_configuration_is_service_scoped():
    # Root defaults are shared by every service that uses this repository.
    assert not (ROOT / "railway.json").exists()
    assert not (ROOT / "railway.toml").exists()
    # Railway retires Config-as-Code on 2026-12-01: the auth build is selected by the
    # service settings (builder DOCKERFILE, dockerfilePath services/auth/Dockerfile),
    # verified on production and staging on 2026-11-23, not by a file in the repository.
    assert not (ROOT / "services/auth/railway.json").exists()
    assert not (ROOT / "services/auth/railway.toml").exists()


def test_railway_auth_runbook_names_the_dashboard_dockerfile():
    runbook = (ROOT / "docs/runbooks/RAILWAY_AUTH_DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "`services/auth/Dockerfile`" in runbook
    assert "/services/auth/railway.json" not in runbook, (
        "Config-as-Code retired 2026-11-23: the auth build is set in Railway service settings, "
        "so a runbook pointing at the deleted file would re-teach the drift"
    )
    assert (ROOT / "services/auth/Dockerfile").is_file()


def test_railway_auth_dockerfile_requires_repository_root_context():
    dockerfile = ROOT / "services/auth/Dockerfile"
    sources = []
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        if line.startswith("COPY "):
            sources.extend(shlex.split(line)[1:-1])
    assert "shared/" in sources
    assert "services/auth/requirements.txt" in sources
    for source in sources:
        assert (ROOT / source).exists(), source

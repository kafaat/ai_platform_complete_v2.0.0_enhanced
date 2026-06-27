from pathlib import Path
import subprocess
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
    base = yaml.safe_load((ROOT / "helm/sahool/values.yaml").read_text())
    prod = yaml.safe_load((ROOT / "helm/sahool/values-production.yaml").read_text())
    workloads = base["workloads"]
    for name, override in prod.get("workloads", {}).items():
        merged = {**workloads[name], **override}
        assert merged["replicas"] >= 2, name
        assert not merged["image"].endswith(":latest"), name
    assert prod["global"]["environment"] == "production"


def test_templates_have_runtime_hardening_contracts():
    text = (ROOT / "helm/sahool/templates/deployments.yaml").read_text()
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
    text = (ROOT / "helm/sahool/templates/migration-job.yaml").read_text()
    assert "JOBS_DATABASE_URL" in text
    assert "DATABASE_URL" not in text.replace("JOBS_DATABASE_URL", "")
    assert "helm.sh/hook: pre-install,pre-upgrade" in text


def test_deployment_readiness_validator_passes_for_production():
    result = subprocess.run(
        ["python", "scripts/deploy/validate_helm_readiness.py", "--env", "production"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout

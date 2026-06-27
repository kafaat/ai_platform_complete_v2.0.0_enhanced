# Phase 15 — Deployment Automation + Helm/GitOps Readiness

## Scope

This phase adds a production-oriented deployment layer for SAHOOL without changing the runtime behavior of the existing Docker Compose path.

## Added assets

- `helm/sahool/Chart.yaml`
- `helm/sahool/values.yaml`
- `helm/sahool/values-staging.yaml`
- `helm/sahool/values-production.yaml`
- `helm/sahool/templates/*`
- `scripts/deploy/validate_helm_readiness.py`
- `scripts/deploy/deploy_staging.sh`
- `scripts/deploy/deploy_production.sh`
- `tests/deploy/test_phase15_deployment_readiness_contracts.py`

## Production contracts

The deployment validator enforces:

- production workloads use non-`latest` image tags;
- production replicas are >= 2 for critical services;
- runtime database role remains `sahool_app`;
- job/migration database role remains `sahool_jobs`;
- database URLs and agent/CDSE/JWT values come from Kubernetes Secret references;
- workloads include readiness/liveness probes;
- containers run as non-root with privilege escalation disabled;
- default NetworkPolicy exists;
- migration runs as a Helm pre-install/pre-upgrade hook.

## Deployment command

```bash
./scripts/deploy/deploy_staging.sh
./scripts/deploy/deploy_production.sh
```

Production deployment intentionally runs the existing gates before Helm:

```bash
./scripts/production_validation_gate.sh
python scripts/observability/validate_observability_assets.py
python scripts/deploy/validate_helm_readiness.py --env production
python scripts/release/validate_release_package.py
```

## Limitations

This environment did not provide a Kubernetes cluster or Helm binary, so validation is static and contract-based. The next live step is to run `helm template`, `helm lint`, and a staging deployment in a real cluster.

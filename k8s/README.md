# SAHOOL Kubernetes Deployment

This directory is intentionally thin: the supported deployment path is the Helm chart in `helm/sahool`.
Use `helm/sahool/values-staging.yaml` for staging and `helm/sahool/values-production.yaml` for production.

Required gates before deployment:

```bash
./scripts/production_validation_gate.sh
python scripts/deploy/validate_helm_readiness.py --env production
python scripts/release/validate_release_package.py
```

Secrets must be provided by External Secrets, Sealed Secrets, or the cloud secret manager. Do not deploy placeholder secrets.

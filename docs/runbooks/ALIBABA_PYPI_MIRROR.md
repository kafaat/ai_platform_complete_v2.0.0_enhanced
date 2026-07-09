# Alibaba Cloud PyPI Mirror Contract

SAHOOL uses exact direct dependency pins in `services/**/requirements*.txt`. True transitive lock compilation still needs a connected package index.

The current decision is:

```text
Default package index: https://pypi.org/simple
Optional regional mirror: https://mirrors.aliyun.com/pypi/simple/
```

Alibaba Cloud PyPI is supported as a first-class override for CI runners or operator environments where official PyPI is slow, blocked, or routed poorly.

## Default behavior

The helper below defaults to official PyPI and remains operator-overridable:

```bash
source scripts/ci/pip_mirror_env.sh
```

Default exports:

```bash
PIP_INDEX_URL=https://pypi.org/simple
PYPI_MIRROR_URL=https://pypi.org/simple
PIP_TRUSTED_HOST=
PIP_DEFAULT_TIMEOUT=60
PIP_RETRIES=5
```

## Use Alibaba mirror explicitly

For Alibaba Cloud PyPI, override at runtime:

```bash
PYPI_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/ \
PIP_TRUSTED_HOST=mirrors.aliyun.com \
scripts/ci/compile_transitive_service_locks.sh
```

For Docker builds:

```bash
docker build \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  -f services/weather-service/Dockerfile \
  -t sahool-weather-service:local \
  .
```

The Dockerfiles still default to official PyPI, but every pip install is guarded with explicit `--timeout` and `--retries`.

## Compile transitive service locks

```bash
scripts/ci/compile_transitive_service_locks.sh
```

The script runs `pip-tools` and writes per-service `requirements.lock` files next to each service `requirements.txt`.

## Override for private mirrors

For an enterprise/private mirror, do not edit repository files. Override at runtime:

```bash
PYPI_MIRROR_URL=https://pypi.example.internal/simple/ \
PIP_TRUSTED_HOST=pypi.example.internal \
scripts/ci/compile_transitive_service_locks.sh
```

Do not embed credentials in mirror URLs. Use CI secrets, `.netrc`, keyring, or package-index credentials managed by the runner.

## Offline limitation

This repo includes direct pins and mirror-aware lock scripts. It does not claim that transitive locks were compiled offline. True transitive locks must be generated in a connected CI runner or with an internal PyPI mirror.

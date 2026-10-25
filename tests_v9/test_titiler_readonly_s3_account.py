"""Legacy TiTiler's S3 account is read-only on the raster bucket and never the admin key.

TITILER-LEGACY-USES-SHARED-ADMIN-S3-KEY-01: Compose fed the legacy TiTiler the shared
S3_ACCESS_KEY / S3_SECRET_KEY, which .env.example ties to the MinIO admin user. Offline:
the live allow/deny proof runs in scripts/ci/run_s3_compose_slice_acceptance.sh.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "deploy/minio/policies/legacy-titiler.json"
PROVISION = ROOT / "scripts/minio/provision.sh"
RUNNER = ROOT / "scripts/ci/run_s3_compose_slice_acceptance.sh"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minio_gate():
    return _load("sahool_minio_gate_titiler", "scripts/ci/minio_s3_contract_gate.py")


def _compose_gate():
    return _load("sahool_compose_gate_titiler", "scripts/ci/compose_env_contract_gate.py")


def _services():
    return yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))["services"]


def _policy():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_policy_is_list_and_get_on_the_raster_bucket_only():
    assert _minio_gate().legacy_titiler_policy_errors(_policy()) == []


def _widen(mutate):
    policy = copy.deepcopy(_policy())
    mutate(policy["Statement"])
    return policy


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s[1]["Action"].append("s3:PutObject"),
        lambda s: s[1]["Action"].append("s3:DeleteObject"),
        lambda s: s[1].update(Action=["s3:*"]),
        lambda s: s[1].update(Action=["s3:Get*"]),
        lambda s: s[1].update(Resource=["arn:aws:s3:::*"]),
        lambda s: s[1]["Resource"].append("arn:aws:s3:::sahool-scout-ingest/*"),
        lambda s: s[0].update(Resource=["arn:aws:s3:::sahool-scout-ingest"]),
        lambda s: s.append({"Effect": "Allow", "Action": ["admin:*"], "Resource": ["*"]}),
        lambda s: s.append(copy.deepcopy(s[1])),
        lambda s: s[1].update(Condition={"StringLike": {"s3:prefix": "*"}}),
        lambda s: s[0].update(Effect="Deny"),
        lambda s: s[1].update(Action="s3:GetObject"),
        lambda s: s.pop(),
    ],
    ids=[
        "put",
        "delete",
        "s3-star",
        "get-wildcard",
        "any-bucket",
        "scout-objects",
        "scout-list",
        "admin",
        "duplicate",
        "condition",
        "effect",
        "action-string",
        "missing-get",
    ],
)
def test_any_widening_or_change_of_the_policy_is_refused(mutate):
    assert _minio_gate().legacy_titiler_policy_errors(_widen(mutate))


def _titiler_block() -> str:
    text = PROVISION.read_text(encoding="utf-8")
    start = text.index('TITILER_S3_ACCESS_KEY="${TITILER_S3_ACCESS_KEY:-}"')
    return text[start:]


def test_provisioning_is_optional_paired_and_proves_its_own_denials():
    block = _titiler_block()
    # Both halves or neither; neither means no account at all.
    assert 'if [ -n "$TITILER_S3_ACCESS_KEY" ] || [ -n "$TITILER_S3_SECRET_KEY" ]; then' in block
    assert "must be set together" in block
    assert "legacy TiTiler: no S3 account provisioned (reads local COGs only)" in block
    assert re.search(
        r'mc admin policy attach sahool legacy-titiler --user "\$TITILER_S3_ACCESS_KEY"', block
    )
    assert "mc admin policy create sahool legacy-titiler /policies/legacy-titiler.json" in block
    # Positive read, then a write probe and a cross-bucket probe that must fail.
    assert "mc ls titiler/sahool-rasters >/dev/null" in block
    assert "mc pipe titiler/sahool-rasters/.legacy-titiler-write-probe" in block
    assert "if mc ls titiler/sahool-scout-ingest" in block
    assert block.count("exit 1") >= 3
    # Never borrows the admin or another service's key.
    for foreign in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "RASTER_S3_", "SCOUT_INGEST_S3_"):
        assert foreign not in block.split("else", 1)[0].split("must be set together", 1)[1], foreign


def test_compose_wires_titiler_to_its_own_optional_account():
    services = _services()
    titiler = services["sahool-titiler"]["environment"]
    init = services["sahool-minio-init"]["environment"]
    assert titiler["AWS_ACCESS_KEY_ID"] == "${TITILER_S3_ACCESS_KEY:-}"
    assert titiler["AWS_SECRET_ACCESS_KEY"] == "${TITILER_S3_SECRET_KEY:-}"
    assert init["TITILER_S3_ACCESS_KEY"] == "${TITILER_S3_ACCESS_KEY:-}"
    assert init["TITILER_S3_SECRET_KEY"] == "${TITILER_S3_SECRET_KEY:-}"
    assert _compose_gate().titiler_credential_errors(titiler, init) == []
    assert "./deploy/minio/policies:/policies:ro" in services["sahool-minio-init"]["volumes"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("AWS_ACCESS_KEY_ID", "${S3_ACCESS_KEY:-}"),
        ("AWS_SECRET_ACCESS_KEY", "${S3_SECRET_KEY:-}"),
        ("AWS_ACCESS_KEY_ID", "${MINIO_ROOT_USER:-sahool-admin}"),
        ("AWS_SECRET_ACCESS_KEY", "${MINIO_ROOT_PASSWORD:?}"),
        ("AWS_ACCESS_KEY_ID", "${RASTER_S3_ACCESS_KEY:?}"),
        ("AWS_ACCESS_KEY_ID", "${TITILER_S3_ACCESS_KEY:-sahool-admin}"),
        ("AWS_ACCESS_KEY_ID", "sahool-admin"),
    ],
)
def test_compose_gate_refuses_any_other_titiler_credential_source(key, value):
    services = _services()
    titiler = dict(services["sahool-titiler"]["environment"], **{key: value})
    errors = _compose_gate().titiler_credential_errors(
        titiler, services["sahool-minio-init"]["environment"]
    )
    assert len(errors) == 1 and key in errors[0], errors


@pytest.mark.parametrize(
    "init_value",
    [None, "${TITILER_S3_ACCESS_KEY:?TITILER_S3_ACCESS_KEY required}", "${S3_ACCESS_KEY:-}"],
    ids=["missing", "required-breaks-every-up", "foreign"],
)
def test_compose_gate_requires_minio_init_to_pass_the_optional_account(init_value):
    services = _services()
    init = dict(services["sahool-minio-init"]["environment"])
    if init_value is None:
        del init["TITILER_S3_ACCESS_KEY"]
    else:
        init["TITILER_S3_ACCESS_KEY"] = init_value
    errors = _compose_gate().titiler_credential_errors(
        services["sahool-titiler"]["environment"], init
    )
    assert len(errors) == 1 and "sahool-minio-init" in errors[0], errors


def test_env_template_leaves_the_account_empty():
    env = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key] = value
    assert env["TITILER_S3_ACCESS_KEY"] == "" and env["TITILER_S3_SECRET_KEY"] == ""
    # The shared key stays the admin alias for the services that still read it; TiTiler does not.
    assert env["S3_ACCESS_KEY"] == env["MINIO_ROOT_USER"]


def test_slice_acceptance_proves_allow_deny_and_no_account():
    text = RUNNER.read_text(encoding="utf-8")
    assert 'values["S3_ACCESS_KEY"]' not in text
    assert "TITILER_S3_SECRET_KEY=secrets.token_hex(16)" in text
    for needle in (
        "S3_SLICE_TITILER_ACCOUNT_NOT_PROVISIONED",
        "S3_SLICE_TITILER_KEY_NOT_READ_ONLY",
        "S3_SLICE_TITILER_READ_WITHOUT_ACCOUNT",
        "TITILER_KEY list_rasters ALLOWED",
        "TITILER_KEY get_rasters ALLOWED",
        "TITILER_KEY put_rasters DENIED AccessDenied",
        "TITILER_KEY overwrite_cog DENIED AccessDenied",
        "TITILER_KEY delete_cog DENIED AccessDenied",
        "TITILER_KEY list_scout DENIED AccessDenied",
        "TITILER_KEY put_scout DENIED AccessDenied",
        "TITILER_KEY create_bucket DENIED AccessDenied",
        "-e SLICE_TITILER_ACCESS_KEY -e SLICE_TITILER_SECRET_KEY",
        'set_env TITILER_S3_ACCESS_KEY ""',
    ):
        assert needle in text, needle
    # The secret half is scanned for in the evidence like every generated secret.
    assert "*PASSWORD* | *SECRET* | *TOKEN*" in text

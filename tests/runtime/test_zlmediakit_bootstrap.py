"""Exercise the actual Compose commands using disposable files and credentials."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.runtime.env_doctor import check_compose_required_vars

ROOT = Path(__file__).resolve().parents[2]


def service_command(filename, service, key):
    services = yaml.safe_load((ROOT / filename).read_text(encoding="utf-8"))["services"]
    return services[service][key][-1].replace("$$", "$")


@pytest.mark.parametrize(
    ("config", "secret", "success"),
    [
        ("[api]\nsecret=old\n[other]\nsecret=keep\n", r"a&|\b/=", True),
        ("[api]\nsecret=old\n", "sahool-zlm-dev-secret", False),
        ("[api]\nsecret=old\n", "", False),
        ("[api]\nsecret=old\n", "first\nsecond", False),
        (None, "new", False),
        ("[other]\nsecret=old\n", "new", False),
        ("[api]\nport=80\n", "new", False),
        ("[api]\nsecret=one\nsecret=two\n", "new", False),
    ],
    ids=["literal", "dev", "empty", "multiline", "absent", "section", "key", "duplicate"],
)
def test_config_job(tmp_path, config, secret, success):
    conf = tmp_path / "config.ini"
    if config is not None:
        conf.write_text(config, encoding="utf-8")
    (tmp_path / ".sahool_init").touch()
    command = service_command("docker-compose.v9.yml", "sahool-zlmediakit-config", "entrypoint")
    command = command.replace("/conf/", f"{tmp_path}/")
    result = subprocess.run(
        ["sh", "-c", command],
        env=dict(os.environ, SAHOOL_ENV="production", ZLM_API_SECRET=secret),
        capture_output=True,
        encoding="utf-8",
    )
    assert (result.returncode == 0) == success
    if secret:
        assert secret not in result.stdout + result.stderr
    if config is None:
        assert not conf.exists()
    else:
        expected = config.replace("secret=old", "secret=" + secret) if success else config
        assert conf.read_text(encoding="utf-8") == expected
    assert not list(tmp_path.glob(".config.ini.*"))


@pytest.mark.parametrize(
    ("ref", "valid"),
    [
        ("registry:5000/media@sha256:" + "ab" * 32, True),
        ("media@sha256:" + "0" * 64, False),
        ("media@sha256:REPLACE_WITH_VERIFIED_64_HEX_DIGEST", False),
        ("media:master", False),
        ("media@sha256:abc", False),
    ],
)
def test_image_pin_in_gpu_env_and_production_preflight(tmp_path, ref, valid):
    (tmp_path / "gpu-build.vars").write_text(f"ZLMEDIAKIT_IMAGE={ref}\n", encoding="utf-8")
    checks = []
    check_compose_required_vars(
        tmp_path, checks, [str(ROOT / "docker-compose.v9.yml")], "gpu-build.vars", environ={}
    )
    pin = next(c for c in checks if c.name == "zlmediakit-image-pin")
    assert (pin.status == "pass") == valid

    command = service_command("docker-compose.production.yml", "production-preflight", "command")
    result = subprocess.run(
        ["sh", "-ec", command],
        env=dict(
            os.environ,
            ZLMEDIAKIT_IMAGE=ref,
            SAHOOL_ENV="production",
            FIELD_SERVICE_TENANT_ASSERTION_KEY="x" * 32,
        ),
        capture_output=True,
    )
    assert (result.returncode == 0) == valid


@pytest.mark.parametrize(
    ("user", "query", "valid"),
    [
        ("build_only", "?sslmode=verify-full", False),
        ("sahool_app", "?sslmode=disable", False),
        ("sahool_app", "?sslmode=verify-full", True),
        ("sahool_app", "", True),
    ],
)
def test_auth_dsn_preflight(tmp_path, user, query, valid):
    (tmp_path / "docker-compose.v9.yml").write_text("services: {}\n", encoding="utf-8")
    checks = []
    password = "test-password"
    env = {"DATABASE_URL": f"postgresql://{user}:{password}@sahool-postgres/sahool{query}"}
    check_compose_required_vars(tmp_path, checks, ["docker-compose.v9.yml"], environ=env)
    assert (not any(c.status == "fail" for c in checks)) == valid
    assert password not in repr(checks)

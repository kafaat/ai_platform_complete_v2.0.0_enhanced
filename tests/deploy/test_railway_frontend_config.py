"""Railway adapter contracts; production route definitions remain canonical."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "railway_frontend", ROOT / "deploy/railway/render_frontend.py"
)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
SOURCE = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
ENV = {
    "SAHOOL_AUTH_UPSTREAM": "sahool-auth-main.railway.internal:8000",
    "SAHOOL_PLATFORM_UPSTREAM": "sahool-platform.railway.internal:8000",
    "PORT": "8099",
}


def test_adapter_preserves_routes_and_selects_private_auth():
    config = adapter.render(SOURCE, ENV, ["[fd12::10]", "10.0.0.2"])
    assert "server sahool-auth-main.railway.internal:8000 resolve;" in config
    assert "server sahool-platform.railway.internal:8000 resolve;" in config
    assert "resolver [fd12::10] 10.0.0.2 valid=10s ipv6=off;" in config
    assert "listen 8099;" in config and "listen [::]:8099;" in config
    assert "server sahool-auth:8000" not in config
    assert config.count("auth_request /_auth_verify;") == SOURCE.count(
        "auth_request /_auth_verify;"
    )
    assert "rewrite ^/auth/auth/(.*)$ /v1/auth/$1 break;" in config
    assert "rewrite ^/auth/(.*)$ /v1/auth/$1 break;" in config
    assert "proxy_set_header Host sahool-auth-main.railway.internal:8000;" in config
    assert 'proxy_set_header   X-Tenant-Id     "";' in config


def test_named_upstream_source_is_adapted_without_duplicate_groups():
    # The independent compose DNS fix can land before or after this adapter.
    source = "resolver 127.0.0.11 valid=10s ipv6=off;\nresolver_timeout 5s;\n" + SOURCE
    for name in ("auth", "platform"):
        source = source.replace(f"http://sahool-{name}:8000", f"http://frontend_{name}")
        source = (
            f"upstream frontend_{name} {{\n    zone frontend_{name} 64k;\n"
            f"    server sahool-{name}:8000 resolve;\n}}\n" + source
        )
    config = adapter.render(source, ENV, ["10.0.0.2"])
    assert config.count("upstream frontend_auth {") == 1
    assert "upstream railway_sahool_auth {" not in config
    assert "127.0.0.11" not in config
    assert config.count("resolver_timeout") == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("SAHOOL_AUTH_UPSTREAM", ""),
        ("SAHOOL_PLATFORM_UPSTREAM", ""),
        ("SAHOOL_AUTH_UPSTREAM", "http://user:password@auth:8000"),
        ("SAHOOL_AUTH_UPSTREAM", "auth:8000; include /tmp/injected;"),
        ("SAHOOL_AUTH_UPSTREAM", "auth:8000\nserver evil:80"),
        ("SAHOOL_PLATFORM_UPSTREAM", "platform:65536"),
        ("SAHOOL_PLATFORM_UPSTREAM", "platform..internal:8000"),
        ("PORT", "80"),
        ("PORT", "8080;"),
        ("SAHOOL_DNS_IPV6", "off; include /tmp/injected;"),
    ],
)
def test_invalid_environment_fails_before_writing_config(key, value):
    with pytest.raises(ValueError):
        adapter.render(SOURCE, {**ENV, key: value}, ["10.0.0.2"])


def test_system_dns_supports_ipv4_and_ipv6(tmp_path):
    config = tmp_path / "resolv.conf"
    config.write_text(
        "search railway.internal\nnameserver fd12::10\nnameserver 10.0.0.2 # resolver\n"
    )
    assert adapter.read_nameservers(config) == ["[fd12::10]", "10.0.0.2"]
    config.write_text("search railway.internal\n")
    with pytest.raises(ValueError, match="No nameservers"):
        adapter.read_nameservers(config)


def test_listener_and_upstream_drift_fail_explicitly():
    with pytest.raises(ValueError, match="listener contract"):
        adapter.render(SOURCE.replace("listen 8080;", "listen 9090;"), ENV, ["10.0.0.2"])
    with pytest.raises(ValueError, match="missing the expected"):
        adapter.render(
            SOURCE.replace("sahool-auth:8000", "unexpected-auth:8000"), ENV, ["10.0.0.2"]
        )

"""HELM-AUTH-NO-SMTP-SMS-EGRESS-01: fail-closed, opt-in, operator-managed mail relay.

The SAHOOL chart must never ship an Internet SMTP route for auth, or a fallback to
public HTTPS for SMS. The example relay exists only as labels/Secret references;
actual relay installation and CNI verification require a separate operator gate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"
FIXTURE = ROOT / "tests_v9" / "fixtures" / "helm_auth_mail_relay.yaml"
HELM_RENDER_REQUIRED = os.environ.get("HELM_RENDER_REQUIRED") == "1"


def needs_helm(test):
    skip = pytest.mark.skipif(
        not HELM_RENDER_REQUIRED and shutil.which("helm") is None,
        reason="helm binary not installed",
    )
    return pytest.mark.helm_render(skip(test))


def _run(overlay: str, *, enabled: bool = False, extras: tuple[str, ...] = ()):
    args = [
        "helm", "template", "sahool", str(CHART),
        "-f", str(CHART / "values.yaml"),
        "-f", str(CHART / overlay),
    ]
    if enabled:
        args += ["-f", str(FIXTURE)]
    args += list(extras)
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)


def _docs(result):
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def _named(docs, kind):
    return {d["metadata"]["name"]: d for d in docs if d.get("kind") == kind}


def test_mail_relay_is_off_by_default_in_all_chart_values():
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    assert values["authEmailRelay"]["enabled"] is False
    assert values["authEmailRelay"]["dependencyEgress"] == []
    for overlay in ("values-staging.yaml", "values-production.yaml"):
        extra = yaml.safe_load((CHART / overlay).read_text(encoding="utf-8")) or {}
        assert not (extra.get("authEmailRelay") or {}).get("enabled")
    auth = values["workloads"]["sahool-auth"]
    assert not auth.get("publicHttpsEgress")
    assert all(not key.startswith("SMTP_") and not key.startswith("SMS_")
               for key in (auth.get("env") or {}) | (auth.get("secretEnv") or {}))


@needs_helm
@pytest.mark.parametrize("overlay", ("values-staging.yaml", "values-production.yaml"))
def test_default_renders_no_mail_relay_and_no_auth_smtp_settings(overlay):
    docs = _docs(_run(overlay))
    policy = _named(docs, "NetworkPolicy")
    assert "sahool-auth-mail-relay-egress" not in policy
    assert "sahool-mail-relay-auth-ingress" not in policy
    assert policy["sahool-default-deny"]["spec"]["podSelector"] == {}
    auth = _named(docs, "Deployment")["sahool-auth"]
    env = {item["name"] for item in auth["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert not env.intersection({"SMTP_HOST", "SMTP_PORT", "SMTP_USER",
                                 "SMTP_PASSWORD", "SMTP_FROM",
                                 "SMS_PROVIDER_URL", "SMS_API_KEY"})


@needs_helm
@pytest.mark.parametrize("overlay", ("values-staging.yaml", "values-production.yaml"))
def test_enabled_mail_relay_is_restricted_to_internal_approved_peers(overlay):
    docs = _docs(_run(overlay, enabled=True))
    policy = _named(docs, "NetworkPolicy")
    auth = _named(docs, "Deployment")["sahool-auth"]
    env = {item["name"]: item for item in auth["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["SMTP_HOST"]["value"] == "sahool-mail-relay.sahool.svc.cluster.local"
    assert env["SMTP_PORT"]["value"] == "587"
    assert env["SMTP_FROM"]["value"] == "noreply@sahool.example.invalid"
    for name, key in (("SMTP_USER", "username"), ("SMTP_PASSWORD", "password")):
        assert env[name]["valueFrom"]["secretKeyRef"] == {
            "name": "sahool-mail-relay-credentials", "key": key
        }
        assert "value" not in env[name]
    assert not set(env).intersection({"SMS_PROVIDER_URL", "SMS_API_KEY"})

    default = policy["sahool-default-deny"]["spec"]["podSelector"]
    assert default["matchExpressions"] == [{
        "key": "app.kubernetes.io/component",
        "operator": "NotIn",
        "values": ["sahool-auth"],
    }]
    auth_egress = policy["sahool-auth-mail-relay-egress"]["spec"]
    assert auth_egress["podSelector"]["matchLabels"]["app.kubernetes.io/component"] == "sahool-auth"
    ports = {p["port"] for entry in auth_egress["egress"] for p in entry["ports"]}
    assert ports == {53, 587, 5432, 6379}
    assert not any("ipBlock" in peer
                   for entry in auth_egress["egress"] for peer in entry["to"])
    relay_smtp = [r for r in auth_egress["egress"]
                  if any(p["port"] == 587 for p in r["ports"])]
    assert len(relay_smtp) == 1
    assert relay_smtp[0]["to"] == [{"podSelector": {
        "matchLabels": {"app.kubernetes.io/component": "sahool-mail-relay"}
    }}]
    ingress = policy["sahool-mail-relay-auth-ingress"]["spec"]
    assert ingress["podSelector"]["matchLabels"]["app.kubernetes.io/component"] == "sahool-mail-relay"
    assert ingress["ingress"] == [{
        "from": [{"podSelector": {"matchLabels": {
            "app.kubernetes.io/component": "sahool-auth",
        }}}],
        "ports": [{"protocol": "TCP", "port": 587}],
    }]


@needs_helm
@pytest.mark.parametrize(
    ("extras", "message"),
    [
        (("--set-json", "authEmailRelay.dependencyEgress=[]"), "dependencyEgress"),
        (("--set", "authEmailRelay.port=25"), "port 587"),
        (("--set", "networkPolicy.enabled=false"), "networkPolicy.enabled"),
        (("--set", "workloads.sahool-auth.publicHttpsEgress=true"), "publicHttpsEgress"),
        (("--set", "authEmailRelay.credentialsSecret="), "credentialsSecret"),
        (("--set", "authEmailRelay.podComponent=sahool-auth"), "podComponent"),
    ],
)
def test_invalid_relay_config_fails_render(extras, message):
    result = _run("values-production.yaml", enabled=True, extras=extras)
    assert result.returncode != 0, result.stdout
    assert message in result.stderr, result.stderr

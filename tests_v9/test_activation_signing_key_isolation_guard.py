"""Ledger #3 (producer-key isolation): the activation-gate signing keys must stay isolated.

The activation gate's trust root is a dedicated HMAC secret (ACTIVATION_EVIDENCE_SIGNING_KEY),
with a separate probe secret (ACTIVATION_PROBE_SIGNING_KEY). Both are already provisioned as their
OWN compose variables — never aliased to the service token (SAHOOL_AGENT_TOKEN) or the auth secret
(JWT_SECRET). That isolation is what keeps a leaked service/JWT secret from also forging activation
evidence. This guard LOCKS it: a future compose edit that points either signing key at
``${JWT_SECRET}`` / ``${SAHOOL_AGENT_TOKEN}`` (collapsing the trust boundary) fails CI here.

Scope honesty: this enforces *key isolation in the deployment contract*. Provisioning genuinely
DISTINCT secret VALUES for these variables remains an operator/secret-manager duty (documented in
.env.example) — a static test cannot see runtime secret values. What it can, and does, prevent is a
config change that silently reuses one secret for two trust domains.

Static scan (no infra). Marked unit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")

# The activation signing keys and the foreign secrets they must never be aliased to.
_SIGNING_KEYS = ("ACTIVATION_EVIDENCE_SIGNING_KEY", "ACTIVATION_PROBE_SIGNING_KEY")
_FOREIGN_SECRETS = ("JWT_SECRET", "SAHOOL_AGENT_TOKEN")


def _compose_value(key: str) -> str | None:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", COMPOSE, re.M)
    return m.group(1) if m else None


def test_activation_signing_keys_are_provisioned_in_compose():
    for key in _SIGNING_KEYS:
        assert _compose_value(key) is not None, f"{key} must be set in docker-compose.v9.yml"


def test_activation_signing_keys_are_not_aliased_to_service_or_jwt_secret():
    for key in _SIGNING_KEYS:
        value = _compose_value(key) or ""
        for foreign in _FOREIGN_SECRETS:
            assert f"${{{foreign}" not in value, (
                f"{key} is aliased to ${{{foreign}}} in compose ({value!r}) — this collapses the "
                "activation trust root onto a service/auth secret. Give it its own variable "
                f"(${{{key}...}}); provision a distinct secret value at deploy time."
            )
        # Positive: it must reference its own same-named variable.
        assert f"${{{key}" in value, (
            f"{key} should be sourced from its own ${{{key}...}} variable, got {value!r}."
        )


def test_isolation_guard_would_catch_an_alias_regression():
    # Negative proof: a contrived aliased value is flagged by the substring check.
    contrived = "${JWT_SECRET:-}"
    assert any(f"${{{foreign}" in contrived for foreign in _FOREIGN_SECRETS)

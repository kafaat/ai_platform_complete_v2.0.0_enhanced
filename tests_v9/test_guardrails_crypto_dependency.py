"""Guard the dependency needed by Guardrails' production RS256 verifier."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_guardrails_declares_the_pyjwt_crypto_runtime_extra():
    path = ROOT / "services/guardrails-engine/requirements.txt"
    requirements = [
        Requirement(line.split("#", 1)[0].strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    pyjwt = [item for item in requirements if item.name.lower() == "pyjwt"]
    assert len(pyjwt) == 1
    assert "crypto" in pyjwt[0].extras, (
        "RS256 must be installed in the service image, not just the CI environment"
    )


def test_guardrails_explicitly_declares_cryptography_for_rs256():
    path = ROOT / "services/guardrails-engine/requirements.txt"
    declared = {
        Requirement(line.split("#", 1)[0].strip()).name.lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }
    assert "cryptography" in declared, "The RSA runtime backend must be explicit"

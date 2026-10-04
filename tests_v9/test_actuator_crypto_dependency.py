"""مزوّدُ RSA في صورة المُشغِّل — ACTUATOR-IMAGE-CANNOT-VERIFY-RS256-TOKENS-01.

``_verify_token`` في ``actuator_runtime.py`` يتحقّق بـRS256 متى ضُبط ``JWT_PUBLIC_KEY``، وصورةُ
الخدمة تُثبّت ``requirements.txt`` الخدمة وحده. كان فيه ``PyJWT>=2.13.0`` بلا مزوّد RSA، فبيئةٌ
مبنيّةٌ منه وحده (PyJWT 2.15.1، ``has_crypto False``) ترفض **حتّى التوكن الصالح** بـ401 وسببُه
``InvalidAlgorithmError`` — مقيسٌ باستدعاء ``_verify_token`` الحقيقيّة في بيئةٍ معزولة
(``certification/evidence/actuator_rs256_dependency_proof_20261002.json``).

بيئةُ CI تحمل ``cryptography`` عبوريّاً من ملفّات متطلّباتٍ أخرى، و``aiomqtt`` غائبةٌ عنها عمداً
(فاستيرادُ ``actuator_runtime`` يُتخطّى هنا)؛ لذا يُقاس ما تُثبّته الصورةُ نفسُها، ويُثبَت الوجهان
الموجبُ والسالب بقيود فكّ ``_verify_token`` نفسِها (``algorithms=["RS256"]``، ``audience="sahool"``).
"""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
_SERVICE = ROOT / "services/actuator-service"
_IMAGE_REQUIREMENTS = _SERVICE / "requirements.txt"


def _requirements() -> list[Requirement]:
    return [
        Requirement(line.split("#", 1)[0].strip())
        for line in _IMAGE_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]


def test_the_image_requirements_are_what_the_dockerfile_installs():
    dockerfile = (_SERVICE / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY services/actuator-service/requirements.txt" in dockerfile


def test_the_actuator_verifies_rs256_when_a_public_key_is_set():
    """سببُ وجود هذا الملفّ: إن تخلّى المُشغِّل عن RS256 سقط الاعتمادُ على المزوّد."""
    runtime = (_SERVICE / "actuator_runtime.py").read_text(encoding="utf-8")
    assert 'JWT_ALGORITHM = "RS256" if _JWT_PUBLIC else "HS256"' in runtime
    assert 'algorithms=[JWT_ALGORITHM], audience="sahool"' in runtime


def test_actuator_declares_the_pyjwt_crypto_runtime_extra():
    pyjwt = [item for item in _requirements() if item.name.lower() == "pyjwt"]
    assert len(pyjwt) == 1
    assert "crypto" in pyjwt[0].extras, (
        "RS256 must be installed in the actuator image, not just the CI environment"
    )


def test_actuator_explicitly_pins_cryptography_for_rs256():
    crypto = [item for item in _requirements() if item.name.lower() == "cryptography"]
    assert len(crypto) == 1, "The RSA runtime backend must be explicit in the image requirements"
    pin = list(crypto[0].specifier)
    assert len(pin) == 1 and pin[0].operator == "==" and "*" not in pin[0].version, (
        "The RSA backend must stay exactly pinned without increasing unpinned debt"
    )


def _rs256_pair():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem, public_pem


_CLAIMS = {"sub": "u-1", "tenant_id": "t-1", "aud": "sahool", "iss": "sahool-auth"}


def test_a_valid_rs256_token_verifies_and_forged_ones_fail_on_the_signature():
    """بقيود فكّ ``_verify_token``: الصالحُ يُفكّ، والمحرَّفُ والغريبُ يسقطان **كتوقيعٍ باطل**.

    بلا المزوّد يسقط الثلاثةُ بـ``InvalidAlgorithmError`` قبل فحص التوقيع — العطلُ المقيس.
    """
    jwt = pytest.importorskip("jwt")
    from jwt.exceptions import InvalidSignatureError

    private_pem, public_pem = _rs256_pair()
    token = jwt.encode(_CLAIMS, private_pem, algorithm="RS256")
    payload = jwt.decode(token, public_pem, algorithms=["RS256"], audience="sahool")
    assert payload["sub"] == "u-1" and payload["tenant_id"] == "t-1"

    head, body, sig = token.split(".")
    tampered = f"{head}.{body}.{'B' if sig[0] == 'A' else 'A'}{sig[1:]}"
    with pytest.raises(InvalidSignatureError):
        jwt.decode(tampered, public_pem, algorithms=["RS256"], audience="sahool")

    foreign_private, _ = _rs256_pair()
    foreign = jwt.encode(_CLAIMS, foreign_private, algorithm="RS256")
    with pytest.raises(InvalidSignatureError):
        jwt.decode(foreign, public_pem, algorithms=["RS256"], audience="sahool")

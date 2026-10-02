"""مزوّدُ RSA في صورة المنصّة — PLATFORM-IMAGE-CANNOT-VERIFY-RS256-TOKENS-01.

المنصّة تتحقّق بـRS256 متى ضُبط ``JWT_PUBLIC_KEY`` (``api/main.py``)، لكنّ صورتها تُثبّت
``api/requirements.txt`` وحده، ولم يكن فيه ``cryptography``. فـPyJWT بلا مزوّد RSA يرفض كلَّ
توكن RS256 بـ``InvalidAlgorithmError: Algorithm not supported`` ⇒ 401 لكلّ مستخدم.
مقيسٌ حيّاً في staging (2026-10-02): ``pyjwt 2.13.0 has_crypto False`` داخل الحاوية،
و``JWT validation failed: InvalidAlgorithmError`` على كلّ طلبٍ بعد تسجيلٍ ناجح.

بيئةُ CI تحمل ``cryptography`` عبوريّاً من ملفّات متطلّباتٍ أخرى، فاختبارُ تحقّقٍ وقتَ التشغيل
يخضرّ فيها وإن غاب المزوّدُ من الصورة. لذا يُقاس ما تُثبّته الصورةُ نفسُها: ملفُّها. كسابقة
guardrails في #1091 (``test_guardrails_crypto_dependency.py``).
"""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
_IMAGE_REQUIREMENTS = ROOT / "services/sahool-platform/api/requirements.txt"


def _requirements() -> list[Requirement]:
    return [
        Requirement(line.split("#", 1)[0].strip())
        for line in _IMAGE_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]


def test_the_image_requirements_are_what_the_dockerfile_installs():
    dockerfile = (ROOT / "services/sahool-platform/Dockerfile").read_text(encoding="utf-8")
    assert "COPY services/sahool-platform/api/requirements.txt" in dockerfile


def test_platform_declares_the_pyjwt_crypto_runtime_extra():
    pyjwt = [item for item in _requirements() if item.name.lower() == "pyjwt"]
    assert len(pyjwt) == 1
    assert "crypto" in pyjwt[0].extras, (
        "RS256 must be installed in the platform image, not just the CI environment"
    )


def test_platform_explicitly_pins_cryptography_for_rs256():
    crypto = [item for item in _requirements() if item.name.lower() == "cryptography"]
    assert len(crypto) == 1, "The RSA runtime backend must be explicit in the image requirements"
    pin = list(crypto[0].specifier)
    assert len(pin) == 1 and pin[0].operator == "==" and "*" not in pin[0].version, (
        "The RSA backend must stay exactly pinned without increasing unpinned debt"
    )


def _rs256_pair():
    # التخطّي على الحزمة العليا وحدها: ``cryptography`` تستبدل ``serialization`` في
    # ``sys.modules`` بغلافِ إهمالٍ ``__spec__``ـه None، فيقرؤها حارسُ الخمول
    # (``find_spec``) غائبةً وهي مثبَّتة. والوحدتان الفرعيّتان تُستورَدان عاديّاً بعدها.
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


_CLAIMS = {"sub": "u-1", "aud": "sahool", "iss": "sahool-auth"}


def test_an_rs256_token_verifies_with_the_declared_backend():
    """الوجهُ الحيّ: بالمزوّد نفسه، توكنٌ RS256 بمفتاحٍ مولَّد يُفكّ بقيود المنصّة."""
    jwt = pytest.importorskip("jwt")
    from jwt.algorithms import has_crypto

    assert has_crypto
    private_pem, public_pem = _rs256_pair()
    token = jwt.encode(_CLAIMS, private_pem, algorithm="RS256")
    payload = jwt.decode(token, public_pem, algorithms=["RS256"], audience="sahool")
    assert payload["sub"] == "u-1"


def test_a_tampered_or_foreign_rs256_signature_is_rejected_as_a_signature_error():
    """وجهُ الرفض: التوقيعُ المحرَّف والمفتاحُ الغريب يُرفضان **كتوقيعٍ باطل** لا كخوارزميّةٍ مجهولة.

    هذا ما يُفرّق المزوّدَ الحاضر عن الغائب: بلا ``cryptography`` يسقط الاثنان بـ
    ``InvalidAlgorithmError`` قبل فحص التوقيع (العطلُ الذي قِيس في staging).
    """
    jwt = pytest.importorskip("jwt")
    from jwt.exceptions import InvalidSignatureError

    private_pem, public_pem = _rs256_pair()
    token = jwt.encode(_CLAIMS, private_pem, algorithm="RS256")
    head, body, sig = token.split(".")
    tampered = f"{head}.{body}.{'B' if sig[0] == 'A' else 'A'}{sig[1:]}"
    with pytest.raises(InvalidSignatureError):
        jwt.decode(tampered, public_pem, algorithms=["RS256"], audience="sahool")

    foreign_private, _ = _rs256_pair()
    foreign = jwt.encode(_CLAIMS, foreign_private, algorithm="RS256")
    with pytest.raises(InvalidSignatureError):
        jwt.decode(foreign, public_pem, algorithms=["RS256"], audience="sahool")

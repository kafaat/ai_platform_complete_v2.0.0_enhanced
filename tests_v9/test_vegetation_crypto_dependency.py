"""مزوّدُ RSA في صورة تحليل الغطاء النباتيّ — VEGETATION-IMAGE-CANNOT-VERIFY-RS256-TOKENS-01.

الخدمة تتحقّق بـRS256 متى ضُبط ``JWT_PUBLIC_KEY`` (``vegetation_runtime.py``)، وصورتُها تُثبّت
``requirements.txt`` الخدمة وحده. كان فيه ``PyJWT`` بلا مزوّد RSA، والحلُّ الكامل لذلك الملفّ
(26 حزمة) يخلو من ``cryptography`` ⇒ كلُّ توكن RS256 يُرفض بـ``InvalidAlgorithmError`` ⇒ 401
لكلّ طلب. وهو الصنفُ نفسه الذي قِيس حيّاً في المنصّة (#1122) وأُصلح في guardrails (#1091).

بيئةُ CI تحمل ``cryptography`` عبوريّاً من ملفّات متطلّباتٍ أخرى، فيُقاس ما تُثبّته الصورةُ نفسُها.
"""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
_SERVICE = ROOT / "services/vegetation-analysis-service"
_IMAGE_REQUIREMENTS = _SERVICE / "requirements.txt"


def _requirements() -> list[Requirement]:
    return [
        Requirement(line.split("#", 1)[0].strip())
        for line in _IMAGE_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]


def test_the_image_requirements_are_what_the_dockerfile_installs():
    dockerfile = (_SERVICE / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY services/vegetation-analysis-service/requirements.txt" in dockerfile


def test_the_service_verifies_rs256_when_a_public_key_is_set():
    """سببُ وجود هذا الملفّ: إن تخلّت الخدمة عن RS256 سقط الاعتمادُ على المزوّد."""
    runtime = (_SERVICE / "vegetation_runtime.py").read_text(encoding="utf-8")
    assert '"RS256" if _VEG_JWT_PUBLIC else "HS256"' in runtime


def test_vegetation_declares_the_pyjwt_crypto_runtime_extra():
    pyjwt = [item for item in _requirements() if item.name.lower() == "pyjwt"]
    assert len(pyjwt) == 1
    assert "crypto" in pyjwt[0].extras, (
        "RS256 must be installed in the vegetation image, not just the CI environment"
    )


def test_vegetation_explicitly_pins_cryptography_for_rs256():
    crypto = [item for item in _requirements() if item.name.lower() == "cryptography"]
    assert len(crypto) == 1, "The RSA runtime backend must be explicit in the image requirements"
    pin = list(crypto[0].specifier)
    assert len(pin) == 1 and pin[0].operator == "==" and "*" not in pin[0].version, (
        "The RSA backend must stay exactly pinned without increasing unpinned debt"
    )

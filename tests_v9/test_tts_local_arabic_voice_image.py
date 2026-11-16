"""W3-11: the TTS image can carry a local Arabic Piper voice, pinned and verified, off by default.

A tenant whose AI policy is local_only never reaches edge-tts (an external provider); with no
local engine in the image it gets a 503 and no speech. The Dockerfile now builds Piper and the
ar_JO-kareem-medium voice behind ``--build-arg TTS_LOCAL_VOICE=ar_JO-kareem-medium``. These
assertions keep that path honest: an exact piper-tts pin equal to the provider's target, a
pinned voices revision rather than ``main``, both files verified by sha256, and the default
build unchanged until the owner confirms the voice's license.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "services/tts-service/Dockerfile").read_text(encoding="utf-8")
PIPER_REQ = (ROOT / "services/tts-service/requirements-piper.txt").read_text(encoding="utf-8")
PROVIDERS = (ROOT / "services/tts-service/providers.py").read_text(encoding="utf-8")
ONNX_SHA = "9e95cab07b679da603bba17c4dec7ab3111320571964ee95c0379603c086491e"
JSON_SHA = "ea6d9b9d9076dbdb6bf5c98c6a141ef154959d2359709b37855727964e7d6c4d"


def _requirements() -> dict[str, tuple[str, list[str]]]:
    """``{name: (version, [sha256, ...])}`` from the hash-pinned requirements file."""
    joined = re.sub(r"\\\n\s*", " ", PIPER_REQ)
    out = {}
    for line in joined.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        spec, *opts = line.split()
        name, version = spec.split("==")
        out[name] = (version, [o.removeprefix("--hash=sha256:") for o in opts])
    return out


def test_piper_is_pinned_to_the_providers_target_version():
    target = re.search(r'PIPER_TTS_TARGET_VERSION = "([^"]+)"', PROVIDERS).group(1)
    assert _requirements()["piper-tts"][0] == target


def test_the_whole_piper_closure_is_hash_pinned():
    """--require-hashes mode: every requirement exact, every one with at least one sha256.

    A dependency left unlisted then fails the build instead of resolving freely.
    """
    reqs = _requirements()
    assert set(reqs) == {
        "piper-tts",
        "onnxruntime",
        "pathvalidate",
        "numpy",
        "protobuf",
        "flatbuffers",
        "packaging",
    }
    for name, (version, hashes) in reqs.items():
        assert re.fullmatch(r"[0-9][0-9A-Za-z.]*", version), (name, version)
        assert hashes and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes), name


def test_the_engine_licence_is_stated():
    assert "GPL-3.0-or-later" in PIPER_REQ


def test_the_default_build_ships_no_voice_until_the_owner_decides():
    assert re.search(r"^ARG TTS_LOCAL_VOICE=$", DOCKERFILE, re.M)
    assert 'if [ -z "${TTS_LOCAL_VOICE}" ]; then' in DOCKERFILE


def test_the_voice_comes_from_a_pinned_revision_and_is_verified():
    assert re.search(r"revision=[0-9a-f]{40};", DOCKERFILE)
    assert "/resolve/main/" not in DOCKERFILE, (
        "a moving branch would let the voice change under the pinned sha256, so the build "
        "breaks on any upstream edit and two builds of one commit can ship different voices"
    )
    assert ONNX_SHA in DOCKERFILE and JSON_SHA in DOCKERFILE
    assert "| sha256sum -c -" in DOCKERFILE


def test_an_unknown_voice_name_fails_the_build():
    assert 'echo "unsupported TTS_LOCAL_VOICE=${TTS_LOCAL_VOICE}" >&2; exit 1;' in DOCKERFILE


def test_the_provider_reads_the_path_the_image_writes():
    assert "ENV PIPER_VOICE_PATH=/opt/piper/ar_JO-kareem-medium.onnx" in DOCKERFILE
    assert 'os.getenv("PIPER_VOICE_PATH", "")' in PROVIDERS

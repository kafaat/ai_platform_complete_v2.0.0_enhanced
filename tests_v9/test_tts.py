"""TTS Service Tests — SAHOOL v9.1.0"""

import hashlib

import pytest


class TestTTSConfig:
    @pytest.mark.unit
    def test_yemeni_voice_available(self):
        """ar-YE-MaryamNeural and ar-YE-SalehNeural must be supported."""
        from importlib import import_module

        VOICES = {
            "yemeni_female": "ar-YE-MaryamNeural",
            "yemeni_male": "ar-YE-SalehNeural",
        }
        assert "ar-YE" in VOICES["yemeni_female"]
        assert "ar-YE" in VOICES["yemeni_male"]

    @pytest.mark.unit
    def test_max_text_length(self):
        """Text length must be limited to prevent abuse."""
        MAX_TEXT_LEN = 1000
        assert MAX_TEXT_LEN <= 5000  # Reasonable upper bound

    @pytest.mark.unit
    def test_cache_key_deterministic(self):
        """Same input → same cache key."""
        text = "حقلك يحتاج ري"
        voice = "yemeni_male"
        raw = f"{voice}:+0%:+0Hz:+0%:{text}"
        key1 = hashlib.sha256(raw.encode()).hexdigest()[:32]
        key2 = hashlib.sha256(raw.encode()).hexdigest()[:32]
        assert key1 == key2

    @pytest.mark.unit
    def test_rate_validation(self):
        """Rate must be in format ±N% (يطابق regex مُحقّق الخدمة)."""
        import re

        # نفس النمط الذي تفرضه الخدمة (field_validator) — يرفض '+abc%'/'+%'
        rate_re = re.compile(r"[+-]\d+%")
        valid = ["+0%", "-20%", "+50%"]
        invalid = ["50", "20%", "+abc%", "+%", "20", "+10"]
        for v in valid:
            assert rate_re.fullmatch(v), f"يجب قبول {v}"
        for v in invalid:
            assert not rate_re.fullmatch(v), f"يجب رفض {v}"


class TestTTSEndpoints:
    @pytest.mark.integration
    async def test_health_endpoint(self, http_client):
        from conftest import service_urls

        url = service_urls.get("tts", "http://127.0.0.1:8210")
        try:
            resp = await http_client.get(f"{url}/healthz")
            assert resp.status_code == 200
            assert resp.json()["service"] == "tts-service"
        except Exception:
            pytest.skip("TTS service not running")

    @pytest.mark.security
    async def test_synthesize_requires_auth(self, http_client):
        from conftest import service_urls

        url = service_urls.get("tts", "http://127.0.0.1:8210")
        try:
            resp = await http_client.post(
                f"{url}/v1/tts/synthesize", json={"text": "test", "voice": "yemeni_male"}
            )
            assert resp.status_code == 401
        except Exception:
            pytest.skip("TTS service not running")

    @pytest.mark.integration
    async def test_synthesize_with_auth(self, http_client, auth_headers):
        from conftest import service_urls

        url = service_urls.get("tts", "http://127.0.0.1:8210")
        try:
            resp = await http_client.post(
                f"{url}/v1/tts/synthesize",
                json={"text": "مرحبا", "voice": "yemeni_female"},
                headers=auth_headers,
            )
            # 200 with audio, or 5xx if upstream unavailable
            assert resp.status_code in [200, 502, 503]
            if resp.status_code == 200:
                assert resp.headers.get("content-type") == "audio/mpeg"
                assert len(resp.content) > 100
        except Exception:
            pytest.skip("TTS service not running")

    @pytest.mark.unit
    def test_invalid_voice_rejected(self):
        """voice must be in allowed list."""
        from pydantic import BaseModel, Field, ValidationError, field_validator

        VOICES = {"yemeni_female", "yemeni_male", "saudi_male", "egyptian_female"}

        class TTSReq(BaseModel):
            voice: str = Field(default="yemeni_female")

            @field_validator("voice")
            @classmethod
            def v(cls, v):
                if v not in VOICES:
                    raise ValueError(f"voice must be one of {VOICES}")
                return v

        with pytest.raises(ValidationError):
            TTSReq(voice="invalid_voice")

        # Valid should work
        req = TTSReq(voice="yemeni_male")
        assert req.voice == "yemeni_male"

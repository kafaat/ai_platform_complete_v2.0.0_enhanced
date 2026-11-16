# SAHOOL TTS Service — Yemeni Arabic Speech

Microsoft Edge TTS-powered text-to-speech with native Yemeni Arabic voices.

## Available Voices

| Key | Voice | Region |
|-----|-------|--------|
| `yemeni_female`   | `ar-YE-MaryamNeural` | 🇾🇪 Yemen (female) |
| `yemeni_male`     | `ar-YE-SalehNeural`  | 🇾🇪 Yemen (male)   |
| `saudi_male`      | `ar-SA-HamedNeural`  | 🇸🇦 Saudi Arabia (fallback) |
| `egyptian_female` | `ar-EG-SalmaNeural`  | 🇪🇬 Egypt (fallback) |

## API

### POST /v1/tts/synthesize
```json
{
  "text": "حقلك يحتاج ري خلال 24 ساعة",
  "voice": "yemeni_female",
  "rate": "+0%",
  "pitch": "+0Hz",
  "volume": "+0%"
}
```

Returns: `audio/mpeg` (MP3 bytes)

### POST /v1/tts/stream
Same body, returns streaming `audio/mpeg`.

### GET /v1/tts/voices
Returns list of available voices.

## Auth

All endpoints require JWT Bearer token with `aud="sahool"`.

## Cache

Responses cached in Redis for 24h by SHA-256 hash of (voice + rate + pitch + volume + text).

## Integration with Telegram Bot

```python
# In bots/telegram/main.py
import httpx


async def send_voice_alert(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://sahool-tts:8000/v1/tts/synthesize",
            json={"text": text, "voice": "yemeni_male"},
            headers={"Authorization": f"Bearer {SAHOOL_AGENT_TOKEN}"},
        )
    await bot.send_voice(chat_id, BufferedInputFile(resp.content, "alert.mp3"))
```

## Why Edge TTS over Fish-Speech?

| Feature | Fish-Speech | Edge TTS |
|---------|-------------|----------|
| GPU required | 8GB VRAM | 0 |
| Cost | Local compute | Free |
| Yemeni voices | ❌ MSA only | ✅ Native ar-YE |
| Setup complexity | Hours | Minutes |
| Quality for alerts | Excellent | Excellent |

For an agricultural platform serving farmers in rural Yemen with limited
infrastructure, Edge TTS is the pragmatic choice.

## Local Arabic voice for `local_only` tenants (W3-11)

Edge TTS sends the text to Microsoft, so a tenant whose AI policy is `local_only` never
reaches it (`providers.select_provider_for_policy`). Without a local engine in the image, such a
tenant gets a named 503 and no speech.

The image can carry a local Arabic voice (Piper `ar_JO-kareem-medium`). It is **off by default**:

```bash
docker build -f services/tts-service/Dockerfile --build-arg TTS_LOCAL_VOICE=ar_JO-kareem-medium .
```

- `piper-tts==1.8.0` comes from `requirements-piper.txt`, pinned to the provider's
  `PIPER_TTS_TARGET_VERSION`. The file hash-pins the whole closure (piper-tts, onnxruntime,
  pathvalidate, numpy, protobuf, flatbuffers, packaging), so pip runs in `--require-hashes`
  mode and an unlisted dependency or a changed file fails the build. A hash-checked download
  of the closure succeeded for CPython 3.12 on Linux x86_64 and aarch64, and `pip-audit -r
  requirements-piper.txt` found no known vulnerabilities on 2026-11-16.
- **Engine licence:** piper-tts is **GPL-3.0-or-later** (PyPI metadata for 1.8.0). Building the
  voice into the image ships a GPL-3.0 engine; that is part of the owner's decision to enable it.
- Both voice files are fetched from a pinned `rhasspy/piper-voices` revision and verified by
  sha256. The `.onnx` digest equals the LFS oid that Hugging Face publishes.
- **Why it is off:** the voice's model card gives the training-data license only as "See URL"
  (github.com/AliMokhammad/arabicttstrain). Shipping the voice in the default image waits for
  the owner to confirm that license.

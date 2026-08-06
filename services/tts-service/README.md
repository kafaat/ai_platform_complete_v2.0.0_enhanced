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

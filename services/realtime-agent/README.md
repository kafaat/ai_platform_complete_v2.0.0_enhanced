# SAHOOL governed voice worker

This optional native LiveKit AgentServer worker is disabled unless
`SAHOOL_REALTIME_VOICE_ENABLED=1`. The disabled entrypoint exits without importing
LiveKit, opening sockets or loading a model. Enabling requires explicit configuration
and separate operational acceptance. It does not execute agricultural tools.

The worker registers only `sahool-agronomist`. Dispatch metadata contains exactly
`session_id` and `nonce`. Before connecting media it obtains a live session context
from the internal broker, verifies the assigned room, current canonical v2 local-only
policy and expiry, and loads a verified local STT model. The broker authenticates the
user, tenant and field; the worker pins their identities for the lifetime of the job.
Only the assigned participant's microphone is subscribed. Camera, screen audio and
Data Channels are excluded. Published tracks contain audio only.

## Explicit configuration

| Variable | Purpose |
| --- | --- |
| `SAHOOL_REALTIME_VOICE_ENABLED` | `0` by default; only `1` starts a worker |
| `REALTIME_SESSION_ORIGIN` | Trusted bare HTTP(S) broker origin |
| `REALTIME_WORKER_SECRET` | Dedicated internal ASCII credential, 32–256 non-whitespace characters |
| `REALTIME_AI_ORIGIN` | Trusted bare frontend BFF origin for authenticated AI calls |
| `REALTIME_TTS_ORIGIN` | Trusted bare frontend BFF origin for authenticated local speech |
| `REALTIME_TTS_PROVIDER` | `piper` (default) or `xtts`; external speech is rejected |
| `REALTIME_STT_MODEL_PATH` | Absolute path to a complete pre-provisioned faster-whisper model |
| `REALTIME_STT_MODEL_SHA256` | SHA-256 of `model.bin` |
| `REALTIME_STT_BUNDLE_SHA256` | Full directory digest described below |
| `LIVEKIT_URL` | Explicit bare WS(S) SFU origin |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Backend worker registration credentials |

Mount models read-only. No model is bundled or downloaded by the worker. The model
bundle must include `model.bin`, `config.json` and `tokenizer.json`; symlinks are
rejected. To calculate the bundle digest: sort all regular files by relative POSIX
path, then feed each `relative_path + "\n" + file_sha256_hex + "\n"` as UTF-8 into
SHA-256. Every file is included. Both checksums are required. faster-whisper loads
with `local_files_only=True`, CPU int8, two threads and one model worker. GPU support
and acoustic/model quality are not accepted by these tests.

## Execution and limits

Incoming audio is decoded by LiveKit to 16 kHz mono PCM16. The initial energy VAD
requires 40 ms of speech and ends a turn after 700 ms of silence, with a 15-second
input cap. This is an engineering baseline requiring noisy-field Arabic acceptance.
STT is local; the AI request uses the farmer's broker-issued bearer through the
existing authenticated BFF. The provider accepts only persisted, owner-verified
published field facts and requests local TTS with Redis caching bypassed. WAV/MPEG
bytes are decoded through actual PyAV and resampled to 48 kHz mono PCM16 native
LiveKit audio frames. Encoded audio is never sent through Data Channels.

Authorization is revalidated before STT, AI, TTS and publication, and every two
seconds independently. A total five-second broker deadline bounds request lifetime.
A separate expiry timer interrupts stalled connect, publish and participant waits.
A turn has a 45-second deadline. Speech onset supersedes a previous turn and clears
queued audio. Native capture awaits are shielded so interruption retains their FFI
completion listener. Before source reuse, playback waits up to 500 ms for the
actual native acknowledgement and clears the source again. If completion cannot be
confirmed (including repeated cancellation), the outgoing track is muted, the
source becomes unusable and the job ends; uncertain output is never reused.
The single STT executor skips canceled queued inference. Already-running native STT
cannot be preempted by Python cancellation; its output is discarded and worker
process shutdown has a ten-second SDK deadline. This does not claim zero acoustic
tail or native inference hard preemption.

The worker does not persist audio, credentials or transcripts. Existing AI service
audit retention still applies to the submitted question and validated answer; user
consent must disclose that retention. No bearer, transcription, provider response or
raw exception is logged by worker application code.

## Validation boundaries

Run the isolated tests after installing `requirements.txt`, `pytest` and
`pytest-asyncio`: `python -m pytest -q -o addopts='' services/realtime-agent/tests/`.
Tests exercise real SDK configuration/native audio frames, actual PyAV codecs,
revocation, cancellation and provider gates with injected local fixtures. They do
not prove an actual Arabic model, real SFU media round trip, deployed Platform RLS,
TURN, weak networks or physical-device behavior. These remain separate acceptance
requirements before enabling the feature.

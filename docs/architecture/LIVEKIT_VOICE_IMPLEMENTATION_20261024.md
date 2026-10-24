# Opt-in governed voice integration

Base: `9b3d59d95100dfb8cc0faf95cd5da4d5b6039786` (Draft PR #1262). All new voice/call feature flags default to disabled. This candidate is not production acceptance.

## Ownership and transport

LiveKit owns signaling, SFU media and room/worker transport. SAHOOL owns identity, tenant/field authorization, evidence publication, operation approval and auditing. Browser/native microphones publish audio only. No equipment commands or agricultural tools are accepted through a voice data channel.

The session service issues a room-scoped grant after Platform authorization. Optional `voice_consent` is independent of session consent. A fixed `sahool-agronomist` dispatch carries only an opaque session ID and nonce. The worker fetches transient credentials through the internal authenticated job endpoint and revalidates the current tenant policy/field. Credentials are revoked on close, failure, cancellation or expiry; only cleanup IDs survive restart.

The voice worker uses manual LiveKit audio I/O, local offline faster-whisper, the authenticated AI Agronomist BFF and local Piper/XTTS. No default cloud plugin or audio-to-audio model is instantiated. The AI voice path requires the current trusted local-only policy, zero tool rounds and an owner-persisted validated structured facts receipt before speech. Interruption and expiry cancel playback and clear queued native PCM.

## Privacy and clients

AI Agronomist retains its existing question/advice audit. Explicit consent discloses that retention. TTS `no_store` bypasses cache reads and writes; it does not promise global data deletion. No recording or video feature is enabled.

`/realtime-call/` is a distinct top-level Vite document with separate login/MFA and an in-memory bearer. The raw canonical URL alone grants microphone access; alternate paths and embedding are rejected. SPA pages retain capture denial. A second user action enables the microphone. Flutter reuses existing native authentication/field context, requires consent, and stops capture on lifecycle changes and expiry. Reconnection stays muted.

Signed raw LiveKit webhook bodies are verified using the official SDK and deduplicated atomically by ID/digest. Receipt storage excludes payloads and credentials. Events remain hints, with reconciliation and lease authority in the session engine.

## Verification boundaries

Source-focused receipts live in `certification/evidence/realtime_voice_recovery_20261024/`. Real SDK/native PCM, mock provider boundaries, HTTP authorization/cache and browser document checks are reported separately. Full CI, actual SFU deletion/rejoin using both initial and server-refreshed tokens, and Flutter solver/analyzer/native APK build are separate acceptance gates.

The SFU fixture uses an official digest-pinned image and a synthetic RS256 Platform authority. An `auto_create:true` counterexample must admit the captured refreshed bearer after deletion. This does not certify deployed Platform RLS, TURN, weak mobile networks or actual Arabic model quality. The Flutter lock must come from a real solver artifact; it is never fabricated.

## Recovery note

The previous unpublished local candidate `68f8fdb6316add9038423869a7e9b453ebd56870` and scratch logs became unavailable before upload. This implementation was reconstructed from the verified remote foundation. Earlier counts and checks are historical only; new code requires new evidence. No main merge, production deployment, credentials or sharing-policy changes are included.

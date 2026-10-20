# SAHOOL real-time voice/video architecture — source-grounded decision (2026-10-20)

**Status:** Proposed design, not deployed or accepted. **Source baseline:** SAHOOL
`d23b320ae6c437273a8c8a6a1ba9fc5f111b1e1c`; LiveKit
`19b6c603471d00e594b3474adc26365b33fdea14`.

## Decision

Use **LiveKit SFU + LiveKit Agents** for browser/mobile WebRTC media, signaling,
rooms, agent dispatch and reconnection. Keep **SAHOOL** as the exclusive authority
for human identity, tenant/field ownership, AI policy, canonical data, decisions,
approvals and durable business events. Keep NATS for domain events, never raw audio,
credentials, or actuation over a LiveKit DataChannel.

This is informed by:
- LiveKit: documented audio -> STT -> LLM -> TTS pipeline, turn detection,
  barge-in, agent lifecycle/dispatch, room-node affinity and Redis routing.
- Pipecat: transport independence and cancellable, modular processing stages.
- mediasoup: SFU transports are not application authorization or domain logic.

**Do not deploy two SFUs, replace NATS, or silently enable external inference.**

## Source-to-target mapping

| Existing source | Observed behavior | Design decision |
| --- | --- | --- |
| `frontend/src/sections/ChatbotPage.tsx` | POST /api/ai-agronomist/chat + typewriter | new opt-in realtime screen only; keep text fallback |
| `mobile/sahool_app/lib/screens/advisor_screen.dart` | text chat, still image upload | new optional audio session; do not replace image upload |
| `frontend/src/services/websocket.ts` | notification WebSocket, auth ack | remain notifications-only; do not transport RTP/PCM |
| `services/ai_agronomist/ai_evidence_runtime.py` | evidence collection and structured advisory validation | only approved response text may reach TTS |
| `services/tts-service/routers/tts.py` | local full-buffer synthesis; Edge streaming | provide bounded PCM-frame adapter, explicit policy, cancellation |
| `services/video-processor/routers/streams.py` | RTSP/USB processing + ZLMediaKit | keep camera ingest separate from participatory WebRTC |
| `services/sahool-platform/api/field_cameras.py` | camera as low-weight field observation, rejects unvalidated ML diagnoses | video analysis needs separate governance and evidence |
| `frontend/nginx.conf` | denies camera/microphone by default | allow only opt-in /realtime page, browser still prompts |
| `services/tts-service/tts_tenant_policy.py` | v2 external TTS requires explicit grant | reuse contract; require **independent** STT/video consent |

## LiveKit server mechanics verified in Go

1. `pkg/service/server.go`: registers Twirp RoomService, AgentDispatch, Egress,
   Ingress and SIP, plus `/rtc`, `/rtc/v1`, `/whip/v1`, `/agent`.
2. `pkg/service/auth.go`: parses/verifies LiveKit API JWT grants; joining a
   named room is not equivalent to a SAHOOL tenant/field authorization check.
3. `pkg/service/rtcservice.go`: WebSocket signaling validates join request and
   starts the participant session; clients exchange SDP/ICE.
4. `pkg/service/roomallocator.go` + `pkg/routing/redisrouter.go`:
   host/assign each room to an RTC node; Redis coordinates node/room routing.
   Media goes directly from client via ICE/TURN to SFU; **not through Redis**.
5. `pkg/service/agent_dispatch_service.go` + `pkg/agent/worker.go`:
   dispatch service requires room-admin privileges; registered worker gets a job
   and joins room as an authenticated participant.

LiveKit open-source server is NOT an STT, LLM, TTS or agronomy engine.

## Planned trust boundary and endpoints (NOT IMPLEMENTED)

Proposed **separate** `sahool-realtime-session` service behind authenticated BFF:

- `POST /api/realtime/sessions`: authenticate SAHOOL principal and verify
  `tenant_id`, field ownership, role and entitlement; allocate opaque random room
  id; write session lease; sign **short-lived LiveKit participant JWT** with
  `roomJoin=true`, matching opaque room, minimal publish/subscribe capabilities
  and no RoomAdmin/RoomCreate. Return WSS URL, token, expiry, session_id.
- `GET /api/realtime/sessions/{id}`: tenant/actor-bound read of status.
- `DELETE /api/realtime/sessions/{id}`: stop dispatch, revoke access server-side
  (remove participant / close room), mark lease closed; JWT expiration alone does
  not necessarily terminate an already-connected participant.
- `POST /internal/livekit/webhook`: verify LiveKit signature + raw-body digest,
  dedupe with durable event id, reconcile out-of-order/missed events. Never infer
  guaranteed delivery from webhook retries.
- `GET /readyz`: display dependencies, NO token/room secret disclosure.

Issue tokens only on backend with keys from a secret manager. Never expose
LiveKit API secret, worker service secret, camera URL or bearer in browser JS,
websocket URLs, room metadata, telemetry, event payloads or AI prompts. Use
opaque, unpredictable room names; field/tenant mapping stays server-side.
Apply per-tenant concurrency and per-field permissions, server-side revocation,
rate limits, short leases and explicit cleanup.

The browser joins LiveKit at a separate media endpoint (WSS + ICE UDP/TCP/TURN),
not by proxying audio through the SAHOOL REST backend. Do not route the media
traffic through NATS, HTTP chunked TTS or a standard L7-only Railway proxy.

## Agent pipeline and output acceptance

```text
Microphone -> LiveKit audio track -> VAD / turn detector -> Arabic STT
    -> normalize transcript with confidence + request_id
    -> SAHOOL trusted field context / RAG / KG / current ownership
    -> policy + structured-advisory / guardrails checks
    -> accepted, non-executing speech text -> TTS PCM-frame adapter
    -> LiveKit audio publication -> farmer
                 |
             typed tool call -> capability / tenant / approval gate
                              -> domain service (never via media transport)
```

Begin with a **cascaded** STT/LLM/TTS pipeline, rather than end-to-end
speech-to-speech, because auditability and permission gating are requirements.
Support barge-in via cancellation of LLM/TTS/queued audio and explicit
`turn_id`/generation supersession. Never read partial/unvalidated model text
aloud merely to reduce first-audio latency. Pending approvals MUST remain
pending when audio is interrupted or the agent disconnects.

LiveKit node hooks `on_user_turn_completed`, `stt_node`, `llm_node`,
`tts_node`, `transcription_node` are integration points, not independent
authorizers. Server-enforced authorization belongs **before** all tool and
data access, not only to model prompts.

Provider policy: local_only forbids every external STT, LLM, TTS or video
provider; permissions for each modality must be explicit and independent.
When a local provider is unavailable, return a named availability failure,
not an external fallback. TTS v2 deployment skew must be resolved and accepted
on staging before connecting the live agent.

## Video/camera principles

Camera `source_url` is a private capture credential, never a public event or
response field. The preparatory security patch intentionally changes the
video event schema from `source_url` to categorical `source_type`, and the
create response to `source_type`. Audit all consumers before merge.

Do not feed RTSP camera passwords or unconsented participant video into AI.
The current platform's `field_cameras.py` treats images as low-confidence field
observations; the existing mobile pest ML path must undergo product-policy
reconciliation before being advertised as authoritative diagnosis.

## Infrastructure and production constraints

- WSS/API TLS at ingress; TURN/TLS fallback; stable externally reachable UDP
  candidates for SFU media. LiveKit sample defaults to HTTP 7880 behind TLS,
  ICE/TCP 7881, UDP range 50000–60000 or explicitly configured UDP mux.
- Redis for LiveKit's distributed room coordination should use dedicated
  credentials/ACLs and preferably isolated keyspace/instance. Do not reuse
  SAHOOL app Redis keys without ACL/isolation verification.
- Workers/voice-model infrastructure scale independently from SFU;
  configure memory/CPU limits, overload responses, bounded retries,
  cancellation and backpressure.
- Browser `Permissions-Policy` must deny media outside `/realtime` and allow
  self-origin only for the opted-in route; runtime test actual response headers.
- Record latency per turn (speech end -> accepted text -> first audio -> end);
  measure ICE success, RTT, jitter, packet loss, reconnect rate, false barge-in,
  STT accuracy on Yemeni dialect and response policy denials. Do not promise
  millisecond end-to-end reasoning latency.

## Release and adversarial acceptance gates

1. Security: scan event payloads and HTTP responses for source credentials
   under RTSP userinfo and tokenized URLs; verify both NATS and MQTT paths.
2. Security: missing/malformed policy blocks local and external generation,
   all tools and their advertised schemas; tenant A cannot use tenant B room
   or retrieve any of its evidence. Server-side revoke terminates access.
3. Privacy: simulated local_only with network egress instrumented must show
   **zero** external STT/LLM/TTS/video calls. TTS contract v2 must be live.
4. Browser: test denied normal pages versus allowed /realtime; inspect
   Permissions-Policy on exact final deployed response (including edge).
5. Network: WebRTC direct UDP; ICE/TCP and TURN/TLS fallbacks; reconnection
   on weak mobile networks and asymmetric NAT; no credentials in logs.
6. UX: Arabic voice input + answer, interruption during TTS and model work,
   stale answer suppression, model/transport failures, manual text fallback.
7. Agronomy: absent/weak RAG evidence cannot produce fabricated precise
   agronomy; no actuation without domain validation and human approval.
8. Rollout: explicit per-tenant opt-in, staging canary, pinned source + image
   digest, rollback recipe, metrics and no unauthorized deployment.

## Current code patch scope and intentionally deferred work

This branch supplies **preparatory source fixes**, tests, and this contract.
It DOES NOT implement or enable a LiveKit instance, session service, STT model,
agent worker, browser UI or production deployment. Do not mark those tasks
closed based on a static document or GitHub CI alone.

**External references:** https://docs.livekit.io/agents/models/pipelines/ ;
https://docs.livekit.io/agents/logic/nodes/ ;
https://docs.livekit.io/agents/logic/turns/tuning/ ;
https://docs.livekit.io/transport/self-hosting/ports-firewall/ ;
https://docs.pipecat.ai/pipecat/learn/transports/ ;
https://mediasoup.org/documentation/overview/ .

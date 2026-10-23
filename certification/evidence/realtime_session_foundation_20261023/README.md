# Realtime session foundation — source validation

Source checkpoint: `2eebce88ac1a2d2751fb553904d7f0870409702f`, based on merged
`569d01596c2b8d9db3e12e6210103bc5306055df`. This adds a separate, default-disabled
control plane. It does not enable a call screen or deploy a media service.

`validation.json` records 135 passing focused tests without skips and file
digests. The tests exercise trusted Platform identity/FIELD_VIEW reads, tenant
and actor binding, actual SQLite contention/restart persistence, request-body
limits, lifecycle serialization, cleanup failures, and actual SDK token signing.
The LiveKit RPC boundary is substituted; no live room or media was tested.

`dependency-audit.json` covers every one of the 38 distributions in the separately
installed runtime (inventory adjacent), with zero known vulnerabilities reported
by pip-audit 2.10.1. It is not an audit of unrelated service environments.
`http-source-smoke.json` records real source-process HTTP checks in disabled mode;
it is not a Docker image acceptance receipt.

Six parallel roles supplied the Platform adapter, SQLite store, LiveKit adapter,
HTTP API tests, security review/body limits, and service registration/container
documentation. A lock-removal mutation was rejected by the deterministic
HTTP creation/cleanup race test. Source defaults do not assert self-hosted trust
or remote SFU configuration on the operator's behalf.

Self-hosted LiveKit refreshes participant tokens, so the initial token TTL and
session lease are **not** proof of credential revocation. The actual SFU must
disable `room.auto_create`, and live acceptance must prove that both fresh and
refreshed join-only tokens cannot rejoin a deleted room. This is a release hold;
`ListRooms` readiness and the passing SDK tests do not establish it.

Remaining gates include the standalone image/CI workflow, live SFU admission and
cleanup races, tenant pairs, provider consent and Arabic STT/TTS, isolated browser
capture/navigation, and network/TURN behavior. No agricultural tool or actuator
is reachable from this service. No main merge or runtime deployment is claimed.

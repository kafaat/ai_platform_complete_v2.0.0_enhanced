# Isolated real-SFU admission acceptance

This is an executable acceptance candidate. Passing its unit fixtures is not a
claim that LiveKit has run. The GitHub workflow runs the actual digest-pinned
LiveKit1.13.10 image and native Python RTC1.1.21 on a disposable Linux Docker host.
It records exact clean source HEAD/tree before and after the run.

Run from an exact clean checkout with Docker and an isolated Python environment:

```bash
python -m pip install -r tests/acceptance/livekit/requirements.txt
PYTHONDONTWRITEBYTECODE=1 python scripts/ci/run_livekit_acceptance.py \
  --expected-head "$(git rev-parse HEAD)" --output /tmp/livekit-sfu-receipts
```

The output must be outside the source tree. Its sanitized receipt contains only
case names/results, image identity and source identity. Temporary API secrets,
JWTs, room metadata and logs are excluded from uploaded artifacts.

The normal server explicitly uses `room.auto_create: false`. The fixture uses the
real session engine, durable SQLite store, LiveKit administrative SDK and native
RTC joins. Its Platform authority is a synthetic RS256-authenticated HTTP fixture;
this does not establish deployed Platform authentication or PostgreSQL tenant RLS.
It tests denied cross-tenant ownership/field reads, independent tenant rooms,
restricted RoomService/AgentDispatch RPCs, and initial/refreshed token rejoin after
room deletion. Only an actual binary server `SignalResponse.refresh_token` counts
as refresh evidence. Native SDK Authorization is forwarded to one fixed loopback
SFU for both WebSocket signaling and HTTP validation, without arbitrary headers.
A timeout/ICE failure/proxy500 cannot count as a successful admission rejection.

The independent second server starts with `room.auto_create: true`. The captured
server-refreshed credential must recreate its deleted room: this is the required
counterexample explaining why expiry and room deletion alone do not revoke it.

These loopback tests do not certify Arabic STT/TTS quality, worker audio roundtrip,
TURN, poor field networks, physical mobile devices, production data retention,
external proxy policies, autoscaling or production readiness.

# SAHOOL realtime session foundation

Standalone FastAPI control service for tenant- and field-bound LiveKit sessions.
The feature is **disabled by default** (`SAHOOL_REALTIME_ENABLED=0`). Adding this
directory does not enable a frontend route, deploy an SFU, or establish runtime
acceptance. This foundation does not provide STT, an AI worker, a call UI,
recording, or webhooks.

## Trust boundary

SAHOOL Platform verifies the supplied bearer through its `/api/v1/me` interface.
Field access is checked through the existing Platform field-read path and its
`FIELD_VIEW`/RLS enforcement. This service does not open the agricultural database,
accept a caller-selected tenant, or interpret a SAHOOL token as a LiveKit token.
LiveKit administrative credentials stay on the server. A browser receives only
the short-lived participant grant for its assigned opaque room, never an admin
JWT or API secret. Room names, session state, and access checks are server-owned.

Only self-hosted media is in scope. The operator must explicitly set
`SAHOOL_REALTIME_MEDIA_TRUST=self_hosted` independently of enabling the feature;
the image supplies no media-trust default. Do not connect an external inference provider
or infer consent for STT, video analysis, recording, or retention from the
`consent: true` session request. Their contracts and acceptance remain separate.

## HTTP surface

| Method and path | Purpose |
| --- | --- |
| `GET /healthz` | Process liveness; does not certify dependencies. |
| `GET /readyz` | Readiness subject to enabled feature, valid configuration and dependency checks. |
| `POST /api/v1/realtime/sessions` | Authenticated creation with `{"field_id":"…","consent":true}`. |
| `GET /api/v1/realtime/sessions/{id}` | Tenant- and actor-authorized session read. |
| `DELETE /api/v1/realtime/sessions/{id}` | Authorized closure request; returns `202` with state `CLOSING`. |

Session leases govern this service's lifecycle; no webhook receiver is implemented
here. Deleting a self-hosted LiveKit room does not revoke an issued participant
JWT. LiveKit proactively refreshes participant tokens with at least a ten-minute
validity window, so neither the initial 60-second token TTL nor the 300-second
application lease is a revocation horizon. JWT expiration alone also does not
evict an already connected participant. DELETE does not claim immediate revocation
or immediate terminal closure.

The SFU must actually run with automatic room creation disabled:

```yaml
room:
  auto_create: false
```

Participant grants must keep `roomCreate=false`. Together, the SFU's actual
setting and the restricted grant prevent a fresh or refreshed token from
recreating a deleted room, as enforced by LiveKit `ValidateCreateRoom` in the
reviewed Go source (`9644b99247f5bf770e83d61d186315588372e408`). Set
`LIVEKIT_AUTO_CREATE_DISABLED=1` only after
verifying this SFU configuration. This variable is a separate operator
attestation, with no image default; a successful `ListRooms` call cannot
introspect or prove the setting. Require live fresh-token and refreshed-token
join-after-delete acceptance before any release.

The session enters `CLOSING`, retains its quota reservation through the original
300-second lease, and receives no further tokens from this service. Cleanup runs
every five seconds, retries room deletion, and marks the session `CLOSED` only
after `expires_at` and a confirmed deletion. Failures remain visible and
retryable. Verify this lifecycle, restart recovery and LiveKit outage behavior
before allowing any real sessions. This conservative lease/quota workflow does
not itself bound rejoin when the SFU configuration above is absent or incorrect.

## Architecture inventory

The component authority is `operational_coordination`: its persistent SQLite
records own session admission and cleanup obligations, while tenant, field and
agricultural truth remain with Platform. It owns no domain-schema tables. This
explicit category avoids describing the stateful coordinator as stateless or as
the system of record for agricultural data.

## Configuration

| Variable | Required meaning |
| --- | --- |
| `SAHOOL_REALTIME_ENABLED` | Default `0`; intentional opt-in required. |
| `PLATFORM_API_URL` | Trusted Platform base URL, configured by the operator. |
| `LIVEKIT_URL` | Trusted LiveKit administrative HTTP(S) base URL. |
| `LIVEKIT_WS_URL` | Browser-reachable LiveKit `wss://` endpoint. |
| `LIVEKIT_API_KEY` | Server-only LiveKit credential; supply at runtime. |
| `LIVEKIT_API_SECRET` | Server-only secret; supply at runtime, never in the image. |
| `REALTIME_SQLITE_PATH` | Absolute SQLite file path; image default `/data/realtime.sqlite3`. |
| `SAHOOL_REALTIME_MEDIA_TRUST` | Explicit operator declaration `self_hosted`; no default, independent of feature enablement. |
| `LIVEKIT_AUTO_CREATE_DISABLED` | Explicit operator attestation `1` after configuring SFU `room.auto_create: false`; no image default, not introspectable through `ListRooms`. |

Foundation limits are a 300-second application lease, initial 60-second join-token TTL,
two concurrent sessions per tenant, and one per actor. The service is a
**single-node deployment**, with one Uvicorn worker; do not add replicas sharing
SQLite. These timers do not bound refreshed LiveKit token validity or guarantee
revocation. Persistent state is required for lease/quota recovery and cleanup.

## Container

Build from the repository root:

```sh
docker build -f services/realtime-session/Dockerfile -t sahool-realtime-session .
```

The image installs the service's requirements and copies the
`realtime_session` package plus its `main.py` entrypoint shim. Uvicorn loads
`main:app`; the shim re-exports `realtime_session.session_runtime:app`, allowing existing
service inventory to identify the entrypoint without generator changes.
It runs as UID/GID `10001:10001`, listens on port 8000,
and provides a writable `/data` directory. Application code is not writable by
that user. No `shared/` authentication module or database credentials are copied.

Mount a persistent volume at `/data`, writable by UID/GID `10001:10001`, when
running the service. A bind-mounted directory must be provisioned with matching
ownership; the image cannot fix permissions on an already mounted directory.
The Dockerfile deliberately contains no embedded database and no `VOLUME`
instruction: deployment owns the explicit persistent mount. An ephemeral
container filesystem is insufficient for enabling the feature. An alternative
absolute SQLite path requires an equivalent writable persistent mount.

The default image remains disabled. Enabling it requires operator-supplied
runtime secrets and verified Platform/LiveKit endpoints; it is not part of this
build command. Do not put bearer tokens or LiveKit secrets in URLs or logs.

## Optional Compose image target

`docker-compose.v9.yml` declares `sahool-realtime-session` only under the explicit
`realtime-foundation` profile, with `SAHOOL_REALTIME_ENABLED` fixed to `0`, no
published host ports, a non-root read-only root filesystem and a dedicated data
volume. It has no LiveKit credentials, provider configuration or SFU dependency.
This supplies an honest static target for the repository runtime inventory.
Normal profile-free startup does not select it. Selecting the profile alone still
cannot create sessions: liveness is 200 and readiness remains 503.

A separate operator-reviewed deployment override is required to enable sessions
after live SFU admission acceptance. The optional image target is not a deployment
receipt or a successful enabled-readiness probe. Runtime evidence must preserve
this distinction; do not mark the disabled image ready to satisfy a probe.

## Dependency isolation

Install and audit this service's pinned requirements in its own environment.
The LiveKit SDK requires the service's `PyJWT[crypto]==2.15.1`; other images may
retain `2.15.0`. Do not combine these files into one pip resolver invocation or
change unrelated image pins to make a combined audit resolve. Audit the complete
service environment separately, preserving the existing scanners and audits.
The repository's dependency-conflict inventory records this divergence; its
direct-dependency bundle is an inventory, not a globally installable lock.

## Acceptance still required

The service is registered as `experimental-realtime-control-plane` with
`wiring_disposition: intentional-unconsumed`. Its safety tests and isolated CI
job are evidence of the disabled foundation, not of UI consumption. Run the
service tests in its isolated dependency environment:

```sh
python -m pytest -q -o addopts='' tests_v9/test_realtime_session_*.py services/realtime-session/tests/
```

The actual SDK adapter tests live at
`services/realtime-session/tests/test_livekit_adapter.py`; the dedicated
`.github/workflows/realtime-session.yml` job installs and audits the service
requirements independently, exercises these tests, builds the image and checks
its disabled HTTP behavior.

Before deployment or opt-in, exercise authentication rejection, cross-tenant and
cross-actor access, field denial, explicit consent, concurrency quotas,
restricted room grants, `202`/`CLOSING` deletion with quota retention, fresh and
server-refreshed token join attempts after deletion with SFU auto-create disabled,
repeated room deletion, expired lease cleanup, restart
recovery, and LiveKit outage behavior. Build and inspect this container itself;
existing Railway build plans cover a fixed list and do not automatically prove
the new image. Run tests against self-hosted LiveKit and a staging Platform,
then inspect actual network behavior. Source tests and CI do not establish
STT/agent/media readiness, zero provider egress, or production acceptance.

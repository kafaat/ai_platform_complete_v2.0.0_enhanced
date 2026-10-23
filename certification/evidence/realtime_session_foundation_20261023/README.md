# Realtime session foundation — source validation

Source checkpoint: `0fbcd3b68de1a51f205decfb644bbf6965dcdd9a`, based on merged
`5f730646a112ceb770fb89ce194c259e94921f30`. This adds a separate, default-disabled
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

Integration regression correction: the initial root unit preflight at `19b26a99` reported 3 failures, 10,749 passes and 57 skips. Source `36cbe0e3` fixes image installation and explicit farmer UI debt contracts; 67 targeted regression tests pass. Inventory pins reflect measured additions without raising the Platform route budget. Two temporary UI backlog entries expire 2026-11-22; no call document exists or receives capture permissions. A fresh complete preflight is still required.

CI follow-up: the actual isolated Docker build and real disabled-image HTTP checks passed on `ba6b06a4`; see `ci-image.json`. The default-tier preflight also passed on that candidate, with zero failed or skipped steps. Two later CI failures were a shellcheck unused loop variable and three generic detector matches against source identifiers. The follow-up consumes the variable and limits exceptions to the exact reviewed path and extracted value. Runtime code is unchanged; 135 service tests and 30 security-contract tests were rerun. SFU/media acceptance remains open.

`ci-security-corrections.json` records actual pinned Gitleaks range scans, six positive/negative scope witnesses, and Actionlint with ShellCheck plus an SC2034 mutation. The whole working-tree scan reports three findings in unchanged baseline files; none is in a modified file. This is not a claim that the entire repository has zero findings.

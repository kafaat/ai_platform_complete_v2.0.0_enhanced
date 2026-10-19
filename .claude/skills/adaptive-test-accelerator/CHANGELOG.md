# Change log

## v1.1 — 2026-10-19

- Added a read-only CPU/RAM/disk resource profile and zero-worker recommendation when estimated resources cannot support a worker.
- Added a locally executable stdlib-only sequential receipt runner with immutable plan/context hashes, explicit exact plan SHA approval, and non-shell commands.
- Live local verification of Git HEAD/tree/base head/merge-base or declared files. Remote GitHub status remains explicitly out of scope.
- Added per-unit atomic state, JUnit integrity/consistency checking, default rejection of unaccepted skips and mismatched expected test counts, per-unit output SHA, bounded output capture and append-only local checksum-linked transitions.
- Added lock owner safety, no automatic stale-lock release, conservative resource gating, process environment scrubbing and explicit retry of interrupted/failed cases.
- Added synthetic unit/regression tests, including changed base while feature tree stays unchanged, failed/missing JUnit, tampering, interruption, low disk, stale lock and repeat-invocation prevention.
- Added agent-neutral prompt, sample JSON contexts, duration balancing template and decision matrix. No write to real repositories, CI or GitHub.

Caveat: SHA-256 is an integrity checksum for local files, **not third-party attestation**. The optional runner does not cover every test runner, distributed scheduling or remote state. Upstream project acceptance gates remain mandatory.

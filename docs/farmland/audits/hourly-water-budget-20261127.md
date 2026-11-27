# Hourly irrigation recommendation water-budget audit

## Finding

At main commit `db79cf6d33fb8adb900f049d742de229f8616d4b`, the machine's maximum daily application depth was reapplied to every hourly action. The hourly solver also ignored a positive remaining seasonal allocation carried by the canonical capability graph. Both defects concern the recommendations issued for a field and a season.

| Synthetic input | Result from the original algorithm | Corrected result |
| --- | --- | --- |
| Eight hourly windows across UTC midnight, irrigated area 4.5 ha, daily cap 6 mm, event cap 4 mm, required refill 40 mm | 4 mm in each of eight windows, 16 mm per UTC day | 4 mm and 2 mm per day, 12 mm over the two days |
| Three windows across UTC midnight, area 0.5 ha, seasonal balance 95 m³, event cap 10 mm | 50 m³ for each of three windows, 150 m³ | 50 m³ and 45 m³, 95 m³ total |
| Eight windows with disclosed decimal precision, daily cap 1.000001 mm, event cap 0.3333338 mm | Published total 2.666672 mm | Published depths and volumes remain within both caps |

The fix debits the machine depth against each normalized UTC date and the seasonal volume against the complete proposed schedule. An explicit malformed or exhausted seasonal balance blocks the run. An absent or null seasonal cap retains the existing optional field semantics. Remaining demand is reported through the existing degraded result. Fixtures set synthetic energy and water inputs and exercise the recommendation function.

## Source and branch check

- [Hourly scheduling loop at the audited main commit](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/db79cf6d33fb8adb900f049d742de229f8616d4b/services/sahool-platform/api/hourly_energy_aware_irrigation_mpc.py#L312-L386)
- [Canonical graph projection of machine and source limits](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/db79cf6d33fb8adb900f049d742de229f8616d4b/services/sahool-platform/api/canonical_irrigation_capability_graph.py#L315-L333)
- [Runtime invokes this solver with the graph and normalized weather windows](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/db79cf6d33fb8adb900f049d742de229f8616d4b/services/sahool-platform/api/irrigation_runtime_orchestrator.py#L411-L435)
- [Open PR 1649](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/1649) at `2d4ddb45506443495f1b4587fe73bdcb737a5a68` contains independent groundwater containment for well-backed planning. The original hourly solver matched main byte for byte at SHA-256 `92e3e7d72e01b767c29e1cd4611a148a18508bcc93a6a187b5c21b8471ee2f0e`. The candidate was two commits ahead and one behind the main pin, with merge base `5037c4f9279673c1ebe997cee58c40325f7bee40`. [Branch comparison](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/compare/db79cf6d33fb8adb900f049d742de229f8616d4b...2d4ddb45506443495f1b4587fe73bdcb737a5a68)
- Trusted per-well positive allocation, shared-aquifer scheduling, and reservations across independent or concurrent field solves remain outstanding under [issue 1648](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/issues/1648). A daily depth budget bounds this individual recommendation. The recommendation uses the allocation snapshot passed to the solver; it does not reserve or decrement a persisted seasonal allocation.

## Verification

Python 3.12.14, pytest 9.2.0, isolated working copy at the audited main commit.

- Added regressions on the original solver: **9 failed, 8 existing passed**.
- Corrected working copy: **32 passed** (17 hourly solver, 2 canonical knowledge-to-hourly cases, 7 capability graph, 6 canonical well).
- Ruff lint passed. The Ruff formatter requested a line wrap in the solver.
- A separate invocation of the runtime orchestrator and HTTP route suites was interrupted with exit 137. The execution environment disconnected before the original log files and working-copy blob hashes could be transferred. The work branch reconstructs the two source files from the recorded edits. The focused results above were measured on the local working copy; an exact-head rerun, runtime route, PostgreSQL and generated-artifact checks remain pending.

Reproduce the focused green run from the repository root:

```sh
PYTHONPATH=services/sahool-platform python -m pytest -q \
  tests_v9/test_hourly_energy_aware_irrigation_mpc.py \
  tests_v9/test_canonical_knowledge_to_hourly_mpc_runtime.py \
  tests_v9/test_canonical_irrigation_capability_graph.py \
  services/sahool-platform/tests/test_canonical_well_capability.py
```

Reproduce the baseline in a separate clean checkout at the audited main commit by restoring only `tests_v9/test_hourly_energy_aware_irrigation_mpc.py` from this branch, then running the first test module from that checkout. The changes have no controller dispatch, database migration, or deployment step.

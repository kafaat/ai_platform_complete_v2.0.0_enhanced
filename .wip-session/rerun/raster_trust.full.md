You are fixing a P1 security defect and a P2 correctness defect found by a live full-stack runtime audit of kafaat/ai_platform_complete_v2.0.0_enhanced (2026-09-29; the audit's supervisor independently reproduced the security finding live). Your worktree is based on origin/main. Read CLAUDE.md first and obey it.

COMMON RULES: Do NOT push or open PRs. Do NOT run scripts/ci/verify_all_generated.py or scripts/release/build_release_bundle.py. No Railway operations (read-only inspection of repo config only). Do not touch GATE-01 frozen paths (docs/architecture/gate01_policy.json frozen list: services/actuator-service/actuator_runtime.py, services/actuator-service/routers/commands.py, services/sahool-platform/api/phase_runtime_workers.py, services/sahool-platform/api/phase_runtime_store.py, services/sahool-platform/api/event_bus.py, migrations/*, docs/architecture/db_ownership.yml, docs/architecture/physical_effect_boundary_contract.json, scripts_v9/run_migrations.sql) — if a fix lives there, stop and report. Run pip-audit before adding any dependency. No new general-purpose CI guard scripts. An in-flight PR (branch claude/project-exploration-dtjw3p, not yet in main) adds `auth_request` before token injection on nginx.v9.conf `/api/agriai/`, an ai-agronomist healthz location, and a regression test `test_service_token_is_injected_only_behind_auth_request` (tests_v9/test_e2e_findings_regressions.py) requiring every nginx location that injects a non-empty `X-*-Token` to carry `auth_request` — design consistently with that rule. Measure, don't assume; falsify every new test. Code comments are Arabic-leaning prose naming the measured failure; match surrounding style.

TASK 1 (P1 security) — raster-service trusts a caller-supplied tenant. services/raster-service/raster_security_context.py:30 returns `_clean(request.headers.get("X-Tenant-Id")) or _clean(tid) or _clean(tenant_id)` — a header OR a query parameter, with no verification of who is calling. Reproduced live: anyone on the internal network can read another tenant's imagery through raster-service tiles and thumbnails. The front end blocks this (gateway auth) and database RLS holds — first determine precisely what leaks and through which routes (object-store assets/tiles keyed by tenant? routes that bypass RLS?). Fix: raster-service trusts a tenant only when asserted by an authenticated caller — require the service credential (X-Agent-Token vs SAHOOL_AGENT_TOKEN, constant-time comparison; find and reuse the repo's shared comparator standardised in #1069) for requests that assert a tenant, and remove the query-parameter tenant fallback. Enumerate ALL legitimate callers of the affected raster routes: gateway locations in nginx/nginx.v9.conf and frontend/nginx.conf (browser MapLibre/<img> requests reach raster via these after auth_request sets X-Tenant-Id), sahool-platform clients (api/raster_service_client.py and others), raster-tiler/titiler, workers — each must send the credential; nginx injects it only behind auth_request.
CRITICAL Railway constraint: Railway staging runs sahool-raster-service and sahool-frontend from main; the frontend renders frontend/nginx.conf through deploy/railway/render_frontend.py (read it). The Railway frontend currently has NO SAHOOL_AGENT_TOKEN variable (it has PORT, RAILWAY_DOCKERFILE_PATH, SAHOOL_AUTH_UPSTREAM, SAHOOL_PLATFORM_UPSTREAM, SAHOOL_RASTER_SERVICE_UPSTREAM, SAHOOL_RELEASE_CANDIDATE_SHA, SAHOOL_VEGETATION_ANALYSIS_UPSTREAM, VITE_*). A change making raster-service reject untokened calls, merged as-is, would break staging tiles. Design the safest rollout that closes the hole in the canonical compose stack without breaking staging on merge (e.g. enforcement enabled by default in compose, with an explicit, documented enablement order for Railway: set the token on the frontend first, then enable enforcement on raster-service — or equivalent), and report the exact operator steps. Tests: cross-tenant header without credential → rejected; query-param tenant ignored; valid credential + tenant → allowed; gateway locations inject the token only behind auth_request; the Railway renderer handles any new env/header correctly (tests/deploy/test_railway_frontend_config.py).

TASK 2 (P2) — sentinel-hub-mcp (services/mcp_servers/sentinel_hub_server.py). Live audit: the indicator tool trusts a caller-supplied tenant; the fetch tools use a fixed list of demo fields and point at the commercial Sentinel Hub address while holding Copernicus Data Space (CDSE) credentials. Fix: tenant from a verified context using the same service-credential pattern other MCP servers in services/mcp_servers use (check how they authenticate); remove the demo field list (resolve fields from the real source the platform uses, or return an explicit error — never fabricate); use the CDSE endpoints the platform already uses (find the canonical CDSE configuration/client in the repo). Tests.

Run ruff check/format on changed files, bandit HIGH on changed services (`bandit -r <dirs> --severity-level high`), the tests you touched, relevant unit subsets, and `bash scripts/ci/preflight.sh --fast`. Commit in your worktree (`git -c user.name=Claude -c user.email=noreply@anthropic.com commit`), Arabic commit messages in repo style, ending with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Pn1Px72XNWVxDq6QR2Ztgw

Final report (concise): commit SHAs + worktree branch, what leaked and through which routes (measured), callers enumerated, the rollout design and exact Railway operator steps, test + falsification results, limits, anything declined and why.
---

## RE-RUN PROTOCOL (this overrides anything above that conflicts)

This is a **re-run**. A previous agent on this same task was killed by container restarts before it
handed back a report. Its uncommitted working tree was salvaged as ONE unverified commit:
`5113d330` (base `c1044010`). You may read it (`git show 5113d330`, `git show 5113d330:<path>`)
as a **lead only**. Nothing in it counts: it was never tested, reviewed or reported, and `main` has
moved since (≈10 PRs, #1099–#1107). Re-derive every claim, re-measure every defect on YOUR tree, and
never cherry-pick or copy it wholesale. If you reuse an idea from it, say so in the report.

Your worktree is based on current `main` (`bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1`). Re-read each gap row there first: some IDs may
already be closed or changed by the merged PRs. Say so and skip them; don't redo merged work.

### Durability (non-negotiable, because the previous run was lost)

1. **Report file first.** Before any other work, create `/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/raster_trust.report.md` whose first line is
   `STATUS: RUNNING`. After **each** gap ID is finished (fixed, or classified B/C/D), append its
   section to that file immediately. Do not hold findings in memory to write at the end.
2. **Commit after each gap.** Each fixed gap gets its own commit in your worktree, as soon as its
   tests pass: `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`, with a message
   that states the defect, the measurement and the falsification, ending with these two lines:
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
   `Claude-Session: https://claude.ai/code/session_01Pn1Px72XNWVxDq6QR2Ztgw`
   Record the commit SHA in the report section for that gap.
3. **Do not push** (the coordinator integrates). **Do not create branches beyond your worktree's.**
4. When everything is done, change the report's first line to `STATUS: COMPLETE` and end your final
   message with the same summary. If you stop early for any reason, set `STATUS: INCOMPLETE — <why>`.
   A report still reading `RUNNING` will be treated as a failed run, not as silence.

### Scope rules for integration

- **Do not edit `sahool-brain/`.** Instead, put brain-ready text in the report: for each gap, the new
  status (`open`/`fixed`/`verified` — `verified` only for a live measurement), sources as `path:line`,
  and the evidence. The coordinator applies it centrally, citing the final commit SHAs.
- **Do not regenerate generated artifacts** (`verify_all_generated.py --fix`, `build_release_bundle`,
  inventories, catalog) and do not commit files under `*/generated/`, `release/`, or `*.generated.*`.
  The coordinator regenerates once, in a clean tree, after integration. If a test you need fails ONLY
  because an artifact is stale, note it in the report and move on.
- **Frozen/forbidden, unchanged:** `docs/architecture/db_ownership.yml`, `migrations/MANIFEST.txt`,
  `scripts_v9/run_migrations.sql`, every path in `docs/architecture/gate01_policy.json` frozen list;
  no Railway/NATS/database operation of any kind; no credential handling; no new general-purpose guards
  (targeted tests are fine). `FEATURE_NATS_PUBLISHERS` stays off.
- **Held paths:** changes under `agents/**`, `shared/**` or `migrations/**` are allowed only if a gap
  truly requires them. List every such file in the report under `HELD PATHS`: merging them redeploys
  the notification agent on Railway, which currently fails, so the coordinator will hold those commits.
  Keep them in separate commits from everything else.
- Tests: run the targeted tests for what you touch, plus `pytest -m unit` for the areas involved.
  Show each new test going **red** when its fix is reverted (falsification), and record that.
- Do not kill processes by name (`pkill`/`killall`); it has killed the coordinating shell before.
  Kill only PIDs you started.

### Report format (`/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/raster_trust.report.md`)

```
STATUS: RUNNING | COMPLETE | INCOMPLETE — <why>
BASE: bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1
## <GAP-ID>
class: A-fixed | A-already-closed-on-main | B-GATE01 | C-owner | D-live
commit: <sha or —>
defect measured: <command + observed output, before>
fix: <what, where (path:line)>
falsification: <revert → which test red; restore → green>
brain row (proposed status + text): <…>
blocker / decision needed (B/C/D): <…>
## HELD PATHS
<files under agents/ shared/ migrations/, or "none">
## TESTS RUN
<commands + pass/fail/skip counts>
```

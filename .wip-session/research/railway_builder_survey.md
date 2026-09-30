# Railway build-driver survey: configured builder vs the driver that actually ran

Read-only survey, 2026-09-30. Project 33c50993-1110-43eb-8e92-04c15edae51e. Staging = 70cc51f8…, production = 79de27a7…
Tools used: get-service-config (live `config.build` + variable NAMES), list-deployments (status SUCCESS / FAILED / CRASHED / REMOVED), and get-logs on each deployment id (`types:["build"]`, filter `"build driver" OR "load build definition"`).

**How to read the driver column.** Only Railpack builds print a `using build driver …` line. A Dockerfile build prints no driver line. It goes straight to buildkit's `[internal] load build definition from <path>`, which is the evidence quoted below. For example, a filter on just "build driver" returned `[]` for the Dockerfile build 434b8ccc. There are **no CRASHED deployments** anywhere in the project. Every service below has `builder: DOCKERFILE`. Absent envs: sahool-auth has no staging instance. sahool-soil-service and sahool-ai-agronomist have no production instance ("Service has no configuration in this environment").

| service | env | configured builder + dockerfilePath | RAILWAY_DOCKERFILE_PATH var name | latest built deployment (id · created · status · reason) | actual build driver (exact log line) | MISMATCH |
|---|---|---|---|---|---|---|
| sahool-platform | prod | DOCKERFILE · services/sahool-platform/Dockerfile | yes | b3873034 · 2026-09-28 12:40Z · SUCCESS · redeploy | `[internal] load build definition from services/sahool-platform/Dockerfile` | no |
| sahool-platform | staging | DOCKERFILE · services/sahool-platform/Dockerfile | yes | 193dc233 · 2026-09-28 12:40Z · SUCCESS · redeploy | `[internal] load build definition from services/sahool-platform/Dockerfile` | no |
| sahool-auth-main | prod | DOCKERFILE · services/auth/Dockerfile | yes | a177eb8e · 2026-09-30 00:24Z · SUCCESS · deploy | `[internal] load build definition from services/auth/Dockerfile` | no |
| sahool-auth-main | staging | DOCKERFILE · services/auth/Dockerfile | yes | bc7195c1 · 2026-09-30 00:24Z · SUCCESS · deploy | `[internal] load build definition from services/auth/Dockerfile` | no |
| sahool-auth | prod | DOCKERFILE · services/auth/Dockerfile | yes | df8bb825 · 2026-09-28 12:40Z · SUCCESS · redeploy | `[internal] load build definition from services/auth/Dockerfile` | no |
| sahool-frontend | prod | DOCKERFILE · deploy/railway/Dockerfile.frontend | yes | 3d04e090 · 2026-09-30 14:38Z · SUCCESS · deploy | `[internal] load build definition from deploy/railway/Dockerfile.frontend` | no |
| sahool-frontend | staging | DOCKERFILE · deploy/railway/Dockerfile.frontend | yes | 57b47082 · 2026-09-30 14:38Z · SUCCESS · deploy | `[internal] load build definition from deploy/railway/Dockerfile.frontend` | no |
| sahool-raster-service | prod | DOCKERFILE · services/raster-service/Dockerfile | yes | 7cecbf00 · 2026-09-30 05:17Z · SUCCESS · deploy | `[internal] load build definition from services/raster-service/Dockerfile` | no |
| sahool-raster-service | staging | DOCKERFILE · services/raster-service/Dockerfile | yes | 2fe689aa · 2026-09-30 05:17Z · SUCCESS · deploy | `[internal] load build definition from services/raster-service/Dockerfile` | no |
| sahool-raster-main-candidate | prod | DOCKERFILE · services/raster-service/Dockerfile | yes | 7737de13 · 2026-09-30 05:17Z · SUCCESS · deploy | `[internal] load build definition from services/raster-service/Dockerfile` | no |
| sahool-raster-main-candidate | staging | DOCKERFILE · services/raster-service/Dockerfile | yes | 98d96145 · 2026-09-30 05:17Z · SUCCESS · deploy | `[internal] load build definition from services/raster-service/Dockerfile` | no |
| sahool-notification-agent | prod | DOCKERFILE · agents/notification/Dockerfile | yes | b7b739ed · 2026-09-30 01:53Z · SUCCESS · deploy | `[internal] load build definition from agents/notification/Dockerfile` | no |
| sahool-notification-agent | staging | DOCKERFILE · agents/notification/Dockerfile | yes | 34324a40 · 2026-09-30 01:53Z · FAILED · deploy | `[internal] load build definition from agents/notification/Dockerfile` | no |
| **sahool-migrate-main** | **prod** | DOCKERFILE · deploy/railway/Dockerfile.migrate | yes | **600fa8bb · 2026-09-28 12:40Z · FAILED · redeploy** | **`using build driver railpack-v0.40.0` … `✖ Railpack could not determine how to build the app.` … `railpack prepare exited with an error`** | **YES** |
| sahool-migrate-main | staging | DOCKERFILE · deploy/railway/Dockerfile.migrate | yes | 434b8ccc · 2026-09-28 22:04Z · SUCCESS · deploy | `[internal] load build definition from deploy/railway/Dockerfile.migrate` | no (but the previous build, 90e48979, was railpack — see below) |
| sahool-decision-service | prod | DOCKERFILE · services/decision-service/Dockerfile | **no** | cd1282d5 · 2026-09-28 12:40Z · SUCCESS · redeploy | `[internal] load build definition from services/decision-service/Dockerfile` | no |
| sahool-decision-service | staging | DOCKERFILE · services/decision-service/Dockerfile | **no** | c1acd33b · 2026-09-28 12:40Z · SUCCESS · redeploy | `[internal] load build definition from services/decision-service/Dockerfile` | no |
| sahool-guardrails-engine | prod | DOCKERFILE · services/guardrails-engine/Dockerfile | yes | 04cb4ec8 · 2026-09-28 21:10Z · SUCCESS · deploy | `[internal] load build definition from services/guardrails-engine/Dockerfile` | no |
| sahool-guardrails-engine | staging | DOCKERFILE · services/guardrails-engine/Dockerfile | yes | 31d2d170 · 2026-09-28 21:10Z · SUCCESS · deploy | `[internal] load build definition from services/guardrails-engine/Dockerfile` | no |
| sahool-field-management-service | prod | DOCKERFILE · services/field-management-service/Dockerfile | yes | 7ca2e4e1 · 2026-09-28 12:40Z · SUCCESS · redeploy | `[internal] load build definition from services/field-management-service/Dockerfile` | no |
| sahool-field-management-service | staging | DOCKERFILE · services/field-management-service/Dockerfile | yes | 287b7061 · 2026-09-28 12:40Z · SUCCESS · redeploy | `[internal] load build definition from services/field-management-service/Dockerfile` | no |
| sahool-vegetation-analysis | prod | DOCKERFILE · services/vegetation-analysis-service/Dockerfile | yes | df3e8633 · 2026-09-30 05:17Z · SUCCESS · deploy | `[internal] load build definition from services/vegetation-analysis-service/Dockerfile` | no |
| sahool-vegetation-analysis | staging | DOCKERFILE · services/vegetation-analysis-service/Dockerfile | yes | 4b9b4945 · 2026-09-30 05:17Z · SUCCESS · deploy | `[internal] load build definition from services/vegetation-analysis-service/Dockerfile` | no |
| sahool-tts-service | prod | DOCKERFILE · services/tts-service/Dockerfile | yes | 711e9250 · 2026-09-30 00:24Z · SUCCESS · deploy | `[internal] load build definition from services/tts-service/Dockerfile` | no |
| sahool-tts-service | staging | DOCKERFILE · services/tts-service/Dockerfile | yes | 12201ac3 · 2026-09-30 00:24Z · SUCCESS · deploy | `[internal] load build definition from services/tts-service/Dockerfile` | no |
| sahool-soil-service | staging | DOCKERFILE · services/soil-service/Dockerfile | yes | 51d9cda0 · 2026-09-29 13:51Z · SUCCESS · deploy | `[internal] load build definition from services/soil-service/Dockerfile` | no |
| sahool-ai-agronomist | staging | DOCKERFILE · services/ai_agronomist/Dockerfile | yes | e45a9cb4 · 2026-09-30 00:24Z · SUCCESS · deploy | `[internal] load build definition from services/ai_agronomist/Dockerfile` | no |

## sahool-migrate-main build history (every build found; newest first)

**Production.** It has **no SUCCESS deployment at all**. Every deployment after 600fa8bb is SKIPPED (watchPatterns `/migrations/**`, `/deploy/railway/Dockerfile.migrate`), so production has not built since the railpack failure.

| deployment | created | status | reason | commit | driver line |
|---|---|---|---|---|---|
| 600fa8bb | 2026-09-28 12:40Z | FAILED | redeploy | eff473aa | `using build driver railpack-v0.40.0` → `✖ Railpack could not determine how to build the app.` → `railpack prepare exited with an error` |
| 5b5aec8c | 2026-09-26 11:54Z | REMOVED (built OK) | deploy | eff473aa | `[internal] load build definition from deploy/railway/Dockerfile.migrate` |
| c85893c0 | 2026-09-24 20:56Z | REMOVED (built OK) | deploy | c7fe1f81 | `[internal] load build definition from deploy/railway/Dockerfile.migrate` |
| 5cd52f2a | 2026-09-19 14:26Z | FAILED | redeploy | 15c9c7f1 | `[internal] load build definition from services/auth/Dockerfile` (the service was pointed at the auth Dockerfile at that time) |
| a5b423ec | 2026-09-19 14:07Z | FAILED | deploy | 15c9c7f1 | `[internal] load build definition from services/auth/Dockerfile` |
| f5276e5f | 2026-09-19 12:55Z | FAILED | deploy | c3ebd6a7 | `[internal] load build definition from services/auth/Dockerfile` |

**Staging:**

| deployment | created | status | reason | commit | driver line |
|---|---|---|---|---|---|
| 434b8ccc | 2026-09-28 22:04Z | SUCCESS | deploy | 2a8903ab ("Railway Deployment #8a3aec", authored by railway-app[bot]) | `[internal] load build definition from deploy/railway/Dockerfile.migrate` (no driver line) |
| 90e48979 | 2026-09-28 12:40Z | FAILED | redeploy | eff473aa | `using build driver railpack-v0.40.0` → `✖ Railpack could not determine how to build the app.` → `railpack prepare exited with an error` |
| f6be3137 | 2026-09-26 11:54Z | REMOVED (built OK) | deploy | eff473aa | `[internal] load build definition from deploy/railway/Dockerfile.migrate` |
| 95292d49 | 2026-09-24 20:56Z | REMOVED (built OK) | deploy | c7fe1f81 | `[internal] load build definition from deploy/railway/Dockerfile.migrate` |
| 99cff966 | 2026-09-24 00:17Z | REMOVED | deploy | b85984d3 | not fetched |

## Mismatches
1. **sahool-migrate-main / production, 600fa8bb** (latest build): configured DOCKERFILE + `deploy/railway/Dockerfile.migrate`, but it ran `railpack-v0.40.0` and failed with "Railpack could not determine how to build the app."
2. **sahool-migrate-main / staging, 90e48979**: this is not the latest build, because 434b8ccc superseded it. It was the same railpack failure in the same minute.

**No other repo-based service in either environment ever showed a railpack driver in its latest build.**

## Pattern
- **Only one service, and only one moment.** The railpack builds are exactly the two sahool-migrate-main **redeploys at 2026-09-28 12:40Z** (both redeploy snapshots of eff473aa). Every earlier and later sahool-migrate-main build in both envs used the Dockerfile, including the 09-19 redeploy and the 09-24 and 09-26 push deploys.
- **It is not the mass redeploy itself.** The same 12:40Z redeploy wave built with the Dockerfile for platform (prod and staging), auth (prod), auth-main (staging), decision (prod and staging), field-management (prod and staging), guardrails (staging, 20c66910), notification (staging, 20e99d9f) and tts (staging, dfba0734).
- **It is not the `RAILWAY_DOCKERFILE_PATH` variable name.** Every service has that name except sahool-decision-service, and all of them built with the Dockerfile. Variable values were deliberately not read, so whether sahool-migrate-main's value was empty or wrong at 12:40Z is **unverified**.
- **It is not "every redeploy".** The 09-19 sahool-migrate-main redeploy (5cd52f2a) used a Dockerfile.
- **Most likely explanation (inference, not proven):** at 12:40Z on 09-28, sahool-migrate-main's effective build config did not resolve to its Dockerfile. Railway then fell back to Railpack, which auto-detected a repo root with no language entrypoint (`⚠ Script start.sh not found`). The config was different on 09-19 (it pointed at services/auth/Dockerfile), so this service's build config has been edited over time. Config history is not exposed by these tools. The live config now reads DOCKERFILE plus Dockerfile.migrate, and staging's 22:04Z push build honoured it.
- **Production consequence:** there is no successful sahool-migrate-main deployment in production. The last good build, 5b5aec8c, is REMOVED. All later commits SKIP because of watchPatterns, so production will not rebuild until a commit touches `/migrations/**` or the Dockerfile, or someone triggers a deploy manually.

## Side observations and limits
- For sahool-soil-service and sahool-ai-agronomist, staging `config.source` shows only `{"branch":"main"}` and no `repo` key. Their last builds were still from repo commits. I have not investigated this.
- sahool-platform and sahool-auth in production track branch `deploy/sahool-staging-fa92a1f7`, and sahool-platform in staging tracks `deploy/sahool-platform-db-ready-eb6da9df`. The rest track `main`.
- Earlier, a sahool-migrate-main build log fetch returned "Deployment not found". That was my mistyped id, not missing retention: the correct id 5cd52f2a-f788-… was read afterwards. Build logs were available for every deployment I queried; no retention gaps were hit.
- No state-changing tool and no list-variables call was made.

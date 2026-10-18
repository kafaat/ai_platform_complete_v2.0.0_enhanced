# Local evidence — 2026-10-18

Base: `d58cfc5841bb67e23f098a1580eb6b995e6aa4aa`.

- `initial-six-red.txt`: the initial six behavioral regressions, executed against unmodified base sources. All six failed on behavior, not import/setup errors. The test file was subsequently extended.
- `focused-tests.txt`: 78 passing cases on the source hashes in `source-sha256.json`. Includes actual ASGI JWT validation and upstream authorization forwarding with mocked external HTTP, real Pydantic wire validation, pure calculations, evidence preservation and abstention behavior.
- `catalog-tests.txt`: 21 catalog cases passed; the measured unique route count changes1007→1008 for the new vegetation report route, without increasing the platform route budget.
- `ui-tests.txt`: two React behavior tests.
- `typecheck.txt`: successful `npm run typecheck`.
- The initial preflight was interrupted after a locale-test failure and additional review findings. It is not a successful gate receipt. Final preflight uses the repository script with only `/tmp/preflight_step.log` redirected to a task-specific file to prevent another worktree from overwriting diagnostics. No gate is removed or weakened.

No Docker/MinIO/staging deployment, durable report delivery, independently labeled crop-performance measurement or live CDSE incident acceptance is claimed. See `docs/runbooks/CROPWISE_RESEARCH_IMPLEMENTATION_20261018.md` for wire changes and remaining acceptance.

## Integration of PR #1226

Owner requested replacing already-merged #1223 with #1226 in this integration. Main includes #1223 at `fbcc1b88bdf5140df7deb00b4bfb408d4991dfa4`; #1226 was incorporated at `b35bd52a8d10a8272dd0b64c25085c6f851c8cf9`.

Six actual-client regression cases failed before correction. The diagnostic path now omits both server and client cloud filters, rejects incomplete pages and avoids catalogue fallback/retries. Invalid cloud percentages remain unknown. Regular scene selection is unchanged. `cdse-targeted-tests.txt`: 198 passed. `raster-suite.txt`: 639 passed, two PostgreSQL cases skipped because RASTER_TEST_DATABASE_URL is unset. The two initial router-import failures disappeared after installing the existing platform pin python-multipart==0.0.31 in the test environment; no dependency files changed.

No live CDSE call, database acceptance, deployment or gap closure is claimed. The diagnostic probe stays off by default. Final integrated preflight results are recorded in the PR body against the published tree.

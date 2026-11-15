# Codecov: source-aligned reports for four test lanes

The existing Unit Tests lane collects --cov=services in .coverage, whose initial
coverage.xml uses <repo>/services as its source root. We re-export the same
database from the repository root as coverage-unit.xml and validate it,
before uploading with flag unit-tests.

Platform Unit Tests still runs the existing --cov=api --cov=core selection.
Instead of uploading XML generated under the platform working directory (which
can collapse same-named files from api and core), we re-export the same .coverage
database from the repository root with two explicit source globs.
This export uses the platform's own .coveragerc for consistent report exclusions. This produces
Git-relative names such as services/sahool-platform/core/actuator_command.py.

Decision Service Tests runs many pytest commands, some against real PostgreSQL.
PYTEST_ADDOPTS adds coverage collection for decision-service to those *existing*
invocations without changing the selected tests. --cov-append preserves hits
across invocations. A dedicated .coveragerc omits only the
services/decision-service/tests directory so test code is never counted as
product coverage. The root export with this same config creates
coverage-decision-service.xml; the path guard rejects any test-directory entry.

Integration Tests runs the live auth/admin certification steps against real
PostgreSQL and Redis as the restricted role (MFA end-to-end, C-01 tenant scope, the
#1427 authz gates, and the platform denial log). Before 2026-11-14 they ran pytest with
no --cov, so lines exercised only there (services/auth/routers/users.py,
invitations.py, session_tokens.py, sahool-platform api/routers/security_audit.py on
#1427) counted as uncovered. Each of those four steps now adds
--cov=<sources> --cov-append --cov-report= with COVERAGE_FILE=.coverage.integration-auth
(services/auth for the three auth steps, services/sahool-platform/api and core for the
platform step). The selected tests and their assertions are unchanged. A root export
omits services/auth/tests, the guard refuses that prefix and requires hits in the four
files above, and the upload carries flag integration-auth.

The uploads are flagged unit-tests / platform-unit-tests / decision-service-tests /
integration-auth,
using the pre-existing pinned Codecov action and no implicit report search.
scripts/ci/codecov_coverage_guard.py fails closed if generated XML has missing,
duplicate, untracked, unmeasured, or out-of-scope source paths. Codecov merges
reports for a single commit. No global path fixes are needed because XML carries Git-root paths.
Uploads remain non-blocking on provider outages (fail_ci_if_error: false);
codecov.yml delays statuses and comments until all four uploads arrive.
No threshold is configured or lowered.

Acceptance not yet proven until provider CI:
- All three report-generating steps and flagged uploads must pass on one head.
- Compare Codecov's per-file line sets to the corresponding root-relative XML
  for #1367 and #1370, after this CI fix is merged and those PRs are updated.
- 14.28 percent from Codecov and 172/182 (94.51 percent) measured locally on
  #1370 had *different denominators*. Do not claim parity until reconciled.
- No threshold change, exclusion, application change, merge, deploy, or GATE-01
  policy change in this patch. This PR must remain Draft for independent review.

References:
https://docs.codecov.com/docs/flags
https://docs.codecov.com/docs/merging-reports
https://docs.codecov.com/docs/fixing-paths

## Review correction, 2026-11-10

Review #1371 on ef195bec8 found three defects addressed in this revision:
(1) decision-service test files counted as production source;
(2) the Unit Tests XML lacked path validation;
(3) fail_ci_if_error would make required Unit Tests fail on Codecov outages
and coverage statuses could be emitted before all three reports arrived.
The new configuration omits only test source in decision-service, checks all
three Git-relative reports, sets fail_ci_if_error to false, and delays Codecov
notifications until three reports are received.

Local 172/182 diff-line coverage for #1370 was not a Codecov parity result;
reconcile provider file and line sets after the revised uploads are observed.

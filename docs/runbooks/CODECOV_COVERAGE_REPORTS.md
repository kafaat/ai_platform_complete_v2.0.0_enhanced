# Codecov: source-aligned reports for three test lanes

The existing Unit Tests lane uploads root-relative coverage.xml with flag unit-tests.

Platform Unit Tests still runs the existing --cov=api --cov=core selection.
Instead of uploading XML generated under the platform working directory (which
can collapse same-named files from api and core), we re-export the same .coverage
database from the repository root with two explicit source globs. This produces
Git-relative names such as services/sahool-platform/core/actuator_command.py.

Decision Service Tests runs many pytest commands, some against real PostgreSQL.
PYTEST_ADDOPTS adds coverage collection for decision-service to those *existing*
invocations without changing the selected tests. --cov-append preserves hits
across invocations. The root export creates coverage-decision-service.xml.

The uploads are flagged unit-tests / platform-unit-tests / decision-service-tests,
using the pre-existing pinned Codecov action and no implicit report search.
scripts/ci/codecov_coverage_guard.py fails closed if generated XML has missing,
duplicate, untracked, unmeasured, or out-of-scope source paths. Codecov merges
reports for a single commit. Global codecov.yml fixes are not needed because XML
already carries full Git-root paths.

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

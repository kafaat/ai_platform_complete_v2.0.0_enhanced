# External sources (primary project documentation)

Last reviewed: 2026-10-19. Verify command flags against installed versions before use.

- **pytest-xdist** distribution modes, worker overrides, `loadscope`, `loadfile`, `loadgroup`, and `worksteal`: https://pytest-xdist.readthedocs.io/en/stable/distribution.html
- **pytest-split** duration collection, `--splits`, algorithms, ordering cautions: https://github.com/jerry-git/pytest-split and https://pypi.org/project/pytest-split/
- **pytest-testmon** affected test selection built on executed code / Coverage.py: https://www.testmon.org/
- **pytest** cache, last failed, durations and JUnit: https://docs.pytest.org/en/stable/how-to/cache.html and https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files
- **Playwright** sharding, fullyParallel implications and merge-reports: https://playwright.dev/docs/test-sharding
- **Nx** affected task selection: https://nx.dev/docs/features/ci-features/affected
- **Nx** task input hashing and determinism: https://nx.dev/docs/concepts/how-caching-works and https://nx.dev/docs/kb/configure-inputs
- **GitHub Actions** concurrency semantics, including pending runs: https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency
- **Agent Skills** portable skill packaging: https://agentskills.io/specification

Interpretation: measured duration balancing, dependency-aware task selection, and bounded worker scheduling address different bottlenecks. None ensures correctness without stable inputs, test coverage reconciliation, and mandatory gate enforcement.

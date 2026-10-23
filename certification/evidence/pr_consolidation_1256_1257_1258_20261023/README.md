# PR 1256 / 1257 / 1258 consolidation — 2026-10-23

User instruction: consolidate the three open PRs into one reviewable PR. PR #1257 is retained, targeting main; #1256 and #1258 are superseded only once their source/evidence is preserved and the consolidated tree is verified. This instruction does not perform a main merge or deployment.

The exact component heads and log hashes are in `source_heads.json`. All three component heads and main `ccf19539` are ancestors of local source-union checkpoint `11845b174d9870bb6faddc5841c79ea6eeade73d`. Conflicts occurred only in generated artifacts; source, immutable historical evidence and the latest main guard policies were preserved. Generated artifacts are rebuilt for the union.

## Included behavior and evidence

- #1257: canonical weather-service ET0, strict missing/invalid input handling, unknown period totals distinct from real zero, authenticated tenant forwarding and advisory-only submission protection. Existing equations and regional calibration remain unchanged.
- #1256: additive EO/STAC/raster/spatial experiment tooling, its CI workflow, historical evidence and two bounded OTel CVE parsing regressions. No production provider/raster implementation is replaced by those experiments.
- #1258: source-bound security admission receipts for the coherent OTel family and TiTiler certifi. Main #1254 already contains the same six requirement/direct-bundle blobs, so the consolidated diff preserves them rather than reintroducing an old pin or claiming a new dependency change relative to current main.

## Union acceptance measured before artifact regeneration

- ET0, tracing/CVE regression and mutation headroom: **940 passed / 1 live Redis skip** (`et0-tracing-headroom-tests.txt`).
- Offline EO experiments in a separate pinned environment: **17 passed / 1 isolated PostGIS skip** (`eo-offline-tests.txt`). Synthetic local raster contract cases do not establish a real performance/adoption result.
- Main's staging-connection validator unit cases: **15 passed** (`staging-validator-unit-tests.txt`); no Railway command, staging probe, database action or deployment was performed.
- Read-only mutation count: 844, below the unchanged 856 drift ceiling. Main's 843 / 9.14 minute witness and 869 watermark are preserved; no new timing claim or budget increase.

Historical paired STAC parity failures remain failures. Pixel acceptance, live spatial/RLS acceptance and the real 12-scene/100-field matrix are not established by offline tests; historical source-bound receipts are not relabeled as acceptance of the union. Full preflight, artifact convergence and final-head GitHub CI are recorded separately after this source/evidence freeze.

## Integration regression fixed

The first default preflight found that the new bounded OTel CVE subprocess decoded captured text with the host locale. The call now declares `encoding="utf-8"`; the locale guard and its baseline remain unchanged. The failing guard output is `encoding-regression-red-output.txt`. The first preflight was interrupted and is not an accepted full run. The locale/CVE regression suite then passed 32 cases; `encoding-regression-green-final-output.txt` preserves the actual final output chunk, not a complete original log. A fresh default preflight validates the frozen corrected tree.

## Final resumed source validation

The EO workflow now uses per-PR concurrency and PR-only cancellation; non-PR runs have unique groups. The targeted concurrency contracts passed 55/55. All default suites then completed on indexed tree `bb3ee85ec7401729fc19e6efb588af6c0d9935ae`, preserved as source checkpoint `e83810912a3ceefb80f815887382b104b377bb1f`: **10615 unit passed / 57 skipped**, **1016 root tests passed / 8 skipped**, **4777 platform tests passed / 0 skipped**.

The preflight prefix completed all static, selected mutation, brain and generated fix/check phases. Its interrupted unit run is not accepted; the three suites were resumed separately on the identical indexed tree, confirmed before and after execution. This is resumed phase evidence, not a claim that an interrupted command returned success. See `validation.json`, `preflight-completed-phases.txt`, `unit-tests.txt`, `tests-tests.txt` and `platform-tests.txt`. Full security-tier and final published-head CI acceptance remain separate. Final evidence/artifact additions do not change the accepted application, test or workflow blobs.

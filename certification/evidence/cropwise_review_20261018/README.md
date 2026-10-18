# Review correction evidence — PR #1228

Base: 8424b32e68adcdb0207be13347dea9991159c833 (tree 1bdb6a08e81e571c325cd44e7f980b85fba5a21c).

- regressions-before.txt: nine new behavioral cases failed before source edits (old history gap; policy versions; observation key; missing/malformed/naive acquisition dates; null evidence).
- behavior-contracts.txt: 48 passed, including real anomaly HTTP/store recovery and repeated detection for both previous and historical baseline identities, original hash/time preservation, task binding, tenant checks, version checks, rejection of metadata replacement; published JSON schema parity.
- platform-indicators-asgi.txt: 21 passed. The new test runs both real ASGI routers and timeline reader, with external season/raster reads replaced by HTTP transport. Tests both imagery and a successful empty history, missing/planned season context, user authentication rejection versus internal raster-token failure. No live Postgres/RLS assertion.
- raster-suite.txt: 640 passed; 2 PostgreSQL cases skipped because RASTER_TEST_DATABASE_URL is unset. Real temporary GeoTIFF -> grid identity -> actual change route, plus shifted/revision mismatch and legacy abstention. python-multipart 0.0.31 is installed locally; no dependency file changes.
- vegetation-suite.txt: 90 passed. FIELD_SERVICE_TENANT_ASSERTION_KEY set to a synthetic test-only value to satisfy the existing catalog test's runtime requirement; the first attempt without it failed that unchanged test. No service credentials or provider calls.
- indicators-suite.txt: 9 passed.

Withdrawal of wrapper storage grants is covered by the compose contract test; it is not a claim of an authenticated TiTiler storage adapter. Legacy remains. CDSE correction unchanged and probe off by default. Evidence recovery requires original metadata from the trusted task callback; unavailable original evidence remains a documented abstention.

No migration/GATE-01 edits, no deployment, no field calibration or live tenant/storage acceptance. Broader preflight and exact publication head are reported separately in the PR after completion.

Additional checks: baseline callers receive explicit missing-quality/version reasons; timeline and bundle both classify absent quality as not_evaluated. URL path injection is tested through the actual timeline HTTP reader.

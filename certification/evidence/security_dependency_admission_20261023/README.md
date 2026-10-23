# Security dependency admission — OTel API and TiTiler certifi (2026-10-23)

Gap-IDs: `DEP-OTEL-API-CVE-2026-114603-01`, `DEP-TITILER-CERTIFI-PYSEC-2026-4320-01`.

## Source identities and scope

Base: `d23b320ae6c437273a8c8a6a1ba9fc5f111b1e1c`. Published combined **source-only** checkpoint: `8591fc835b2487d389287b8a0699a893a54aeec5`, tree `9ae501dd1f9f2c6ca4cd7821558131323d443415`. A temporary Git index rebuilt the six-file source tree and matched that published tree exactly. The only dependency changes are:

- Reuse the OTel requirements already present in PR #1256, without modifying that PR: SDK/exporter `1.45.1` and FastAPI instrumentation `0.66b1` in platform/auth/notification/test requirement files. Source checkpoint `0d229cb94534dd8e169dce7afee8d00e417d752b` contains these four files and their direct bundle; it is not a claim that all EO experiments in #1256 are included here.
- TiTiler certifi `2026.7.22` → `2026.10.19`. Independent source checkpoint `1b2d8530fef69fd2322ee3db5fbd75b51673f9a6`, tree `e1df5e33e576cbf48a7bee170a53bfd01941cdfe`, contains only this file and its direct bundle.
- Regenerate `requirements.services.direct.lock` with both fixes. It is a direct dependency bundle, not a resolved transitive lock. No other dependency, security exception, baseline, application or test source changes.

The working tree used for each earlier receipt was based on main with the stated source changes, not a fictitious final commit. The named published source checkpoints bind those source-file identities. The later combined documentation/generated commit is not automatically a full-tree accepted head.

## Measured OTel receipt (reused; no repeated tests)

Before: auth requirement audit returned exit 1 for API `1.44.0 / CVE-2026-114603`, fix `1.45.1` (`otel-baseline-audit.txt`). SDK 1.44.0 requires API==1.44.0; upgrading API alone conflicts with that SDK. Published package metadata and a matching-stack resolver dry-run established the coherent 1.45.1/0.66b1 family.

The existing telemetry delivery and requirements pinning/resolution guard tests passed **13/13, no skips**, with installed API/SDK/exporter 1.45.1 and instrumentation 0.66b1 (`otel-acceptance-tests.txt`). This proves instrumentation and in-memory span export. Auth with a configured endpoint was imported/instrumented without entering lifespan; real lifespan startup was tested only with no endpoint. The real exporter was also exercised against an unavailable local collector. Successful network OTLP delivery to a live collector and exploit-specific CVE behavior were not measured by these tests.

## Measured TiTiler receipt

The earlier 32-runtime discovery audit ran against OTel checkpoint `0d229cb9` with the old TiTiler certifi: **31 passed and one failed** (`runtime-discovery.json`). This establishes discovery provenance, not 31 re-run audits on the combined candidate. TiTiler requirements were byte-identical to main at discovery; `baseline-audit.txt` records `certifi 2026.7.22 / PYSEC-2026-4320`, fix `2026.10.19`.

After the one-line certifi update:

- Exact service requirement-file audit exited 0, no known vulnerabilities (`fixed-audit.txt`). No ignored advisory, no `--no-deps`, no relaxed constraint.
- Full pinned service requirements installed in a separate, clean **Python 3.12** environment; `pip check` passed. Actual certifi 2026.10.19, TiTiler application 0.22.4 and rio-tiler 7.9.6.
- The unchanged service ASGI app with **real TiTiler**, not a stub, read a local synthetic COG: `/cog/info` 200, `/cog/tiles/WebMercatorQuad/0/0/0.png` 200 with valid PNG signature, `/metrics` 200 (`smoke.txt`). This smoke ran after OTel source rollback; its dependency scope was only the TiTiler file, unchanged in the combined source.
- Existing wrapper contracts passed **15/15** (`wrapper-contract-tests.txt`). Those separate contracts use a TiTiler stub and verify wrapper/runtime-identity/packaging; they are not the real raster smoke above.

## Combined candidate and limits

The 19-input critical-path audit is derived from the exact command in `.github/workflows/ci.yml` and **passed with exit 0, no known vulnerabilities** for source checkpoint `8591fc835b2487d389287b8a0699a893a54aeec5` (`combined-critical-audit.txt`), without exception or dependency bypass. Earlier OTel/TiTiler receipts remain attached to their source identities; CI must still evaluate the final combined head. No full Security Scan or full-suite green claim is made merely by composing the receipts. ET0 changes are excluded from this security prerequisite and can stack on it for separate review.

Generated artifacts and release metadata are regenerated after this document/source freeze. A generation/check result on the older certifi-only local candidate does not attest this new combined documentation tree.

Docker is absent; no image build/deployment is claimed. TiTiler smoke is a Python 3.12 host test, not a successful remote HTTPS COG fetch. No database action, merge/main update, production deployment or successful live collector delivery is claimed. Source checkpoints were published explicitly.

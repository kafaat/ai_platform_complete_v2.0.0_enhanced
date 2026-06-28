# Phase 14 — Release Packaging + Deployment Readiness Report

## Scope

This phase adds release packaging controls so the SAHOOL production-candidate bundle can be validated as a deployable artifact rather than only a code snapshot.

## Added assets

- `VERSION`
- `RELEASE_NOTES_20260626.md`
- `release/DEPLOYMENT_READINESS_CHECKLIST.md`
- `release/SAHOOL_RELEASE_MANIFEST_20260626.json`
- `release/FILE_CHECKSUMS.sha256`
- `release/SBOM_MINIMAL.json`
- `scripts/release/build_release_bundle.py`
- `scripts/release/validate_release_package.py`
- `tests/release/test_phase14_release_packaging_contracts.py`

## Release gates

The release validation checks:

- Required runtime and security scripts exist.
- Required Phase 4/6/7/8/9/10/11/12/13 reports exist.
- Checksums match the source files.
- Manifest reports no missing critical assets.
- Deployment checklist and release notes are present.

## Remaining external validation

Docker runtime validation cannot be completed inside this execution environment. It must be run on the deployment host using the checklist in `release/DEPLOYMENT_READINESS_CHECKLIST.md`.

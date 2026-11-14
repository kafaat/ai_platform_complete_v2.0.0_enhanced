# SAHOOL agronomic model admission candidate — phase 14 (read-only)

- **Owner remains Decision Service.** No model registry, evaluation run, activation request or traffic controller is created by this change.
- `shared/mlops/agronomic_candidate.py` compares existing tenant-scoped authoritative **evaluation** and **promotion** evidence, artifact SHA-256 and agronomic cohort fingerprint.
- It checks that model-weight, source-dataset, and license receipt digests are present, that independent field and season holdouts exist, and that the dataset-freeze timestamp precedes evaluation.
- It **cannot authenticate licenses, independent samples, data provenance or model bytes on its own**. Only a trusted upstream verifier that checks the actual receipt bytes and licence grants can return eligibility for **independent review**, never activation.
- The optional `scripts/qa/agronomic_model_candidate_preflight.py` deliberately supplies no trusted verifier and always exits nonzero. It is a format diagnostic, not an acceptance route.
- **Not wired into Decision Service's production activation path.** Installing this helper does not close the production model licensing / validation / signoff gap. Future work must connect a trusted, tenant-scoped verifier, the registered evaluation/promotion records, and independent reviewer authorization before enabling a production gate.

Do not infer a commercial license from a model card, a self-declared `commercial_use_allowed` boolean, a dataset URL, or a hash-like string. SHA-256 values are comparison keys until their contents have been verified by an authority.

## Phase 15: environment-bound trusted verifier

The trusted proof verifier now receives four arguments:
`(evaluation, promotion, evidence, target_environment)`. Its authorization
and license checks must be specific to the passed environment. A proof valid
only in staging **must not** be accepted for production. Old three-argument
verifiers fail closed (no review eligibility). This is a read-only review gate,
not a production activation mechanism or evidence authenticity guarantee.

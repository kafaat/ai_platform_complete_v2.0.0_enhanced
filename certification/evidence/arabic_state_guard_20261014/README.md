# Arabic brain state transition guard — 2026-10-14

Gap: `BRAIN-TRANSITION-GUARD-BLIND-TO-ARABIC-STATUS-01`.
Source repair: `cc15632d0d5f200d0660a8b41cd576efbdfab5a1`, based on
`9a50aac3bf71ed42f4fad91a036d49e61d151a52`; exact tree
`f8bc0d056d9c115e764402fe80779f2383b97353`. PR has not yet been created.

The actual CLI previously accepted four brain-only Arabic closure formats
(heading, backticked heading with parenthetical status, explicit section state,
and declared table status column). The retained red run shows 4 failures and
4 positive controls. Independent baseline fixtures reproduced 21 missed claims
and 15 controls. Final independent CLI review passed 40 cases.

The focused suite passed 152 cases. One exact-ID assertion was then added to
the foreign-history table CLI regression and that case reran successfully;
source bytes remained unchanged. Ruff, assertion-presence and mutation static
guards passed. Full preflight and final-head CI are separate gates pending at
this evidence preparation checkpoint; these source witnesses do not claim them.

Arabic combining marks/tatweel and supported leading closure words are read
only in registry status structures. Reviewed historical heading/section chains
are excluded; canonical table rows never inherit another heading's history.
Leading explicit states override historical parentheses. English guards and
report-only canonical measurement remain unchanged.

Limits: no arbitrary Arabic synonyms, narrative predicate interpretation, or
free-prose claim detection. Content outside the brain is required, but the guard
does not prove that content fixes the same gap or meets live acceptance. No live
verification, deployment, database change, or provider call is claimed.

`wave1_guard_source.patch` is the exact source/test repair. Historical intermediate
review receipts remain labeled as such; `wave1_guard_independent_final.json` and
`wave1_guard_verify_a_review.json` bind final source hashes. The witness is stored
as `.py.txt` for reproducibility without registering an executable evidence script.

## PR provenance and completed local validation

The preceding preparation checkpoint is historical. Draft [PR #1183](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/1183) opened at `a00ff740b09c0a20976b231920ecf72d74b3a8a7`, exactly matching tested tree `36fa76cae2768bf08f94e0fc046ea29f94092482`. Repair source and test bytes are unchanged. `provenance.json` retains both checkpoints.

`validation_summary.json` and `validation_gate_receipts.json` preserve actual commands, exit codes, tree identities, complete stdout result counts and log hashes. Native full preflight exited 0 with two explicit security PATH skips; high-severity Bandit and the exact native pip-audit command subsequently passed in the existing security environment. The workflow's separate 19-requirements audit passed too, without changing its exception IDs. Normal and C-locale unit suites each passed 8878 with 39 skips; repository 996 with 8 skips; platform 4586; guard locale 169/169. Six extra guards passed and final opening release packaging verified 6315 checksums. No JUnit output was generated. Raw logs remain scratch receipts; compact command results and hashes are retained here.

`opening_api_identity.json`, `opening_api_range_gates.json`, and `opening_capability_gate.json` bind the actual opening API commit, three committed-range guards, and the checked draft-body hash. The later final provenance commit still requires generation/convergence, release validation, fresh committed-range gates and final-head GitHub CI. This checkpoint claims neither completed final-head CI nor merge/deployment. The separately retained `staged_brain_evidence_review.json` audited the pre-PR evidence and exact one-gap transition; it is not relabeled as a review of these new provenance files.

## Observed canonical merge #1183

Merged at 2026-10-14T17:11:21Z to `56de3d316fd5243253b6f6d38dc38b331bbddf95`; actual tree6a297aae equals the tested final PR head0126ae78. Current PR contexts:65 success,2 source-justified skips;20 required passed. ECR429 setup failures were retried once with no source change. Raw observations and reviewed final-head CI are copied with original/copied hashes in merge_copy_manifest.json. Original source/preparation/publication receipts remain historical and unchanged. No main-CI or deployment conclusion is drawn here.

Post-merge observation for `56de3d316fd5243253b6f6d38dc38b331bbddf95`: `wave1_guard_postmerge_56de3d_railway.json` records 24 SKIPPED records (13 staging, 11 production), all 43 latest deployment IDs and measured settings unchanged, and no staged changes. This establishes no new deployment or live application behavior. `wave1_guard_merged_main_verify_a.json` independently checks merge/main/source identity. Main post-merge CI remains a separate observation.

Independent postmerge main56de CI (`pr1183_postmerge_main_ci_review.json`):64 successful current contexts,1 source-backed conditional skip,all20 required checks and post-run Certification passed; no main retry. This proof belongs to guard main56de, separately from its earlier PRhead0126 proof, Railway SKIPPED records, subsequent waiver main e614, and raster PR1185.

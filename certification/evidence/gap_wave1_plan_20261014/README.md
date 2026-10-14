# Remaining-gap plan snapshot at main 9a50aac3

This is the exact **135 open-ID baseline** at `9a50aac3bf71ed42f4fad91a036d49e61d151a52`, not the live count after
the Arabic guard repair. The baseline has526 IDs:135 open,388 fixed,3 verified.
After the guard-only status change the expected live count is134/389/3; the
owner must measure the actual committed registry before claiming that count.

Every baseline ID has its current canonical registry text, next action, closure
condition provenance, dependencies and deployment limits. The historical136 plan
is preserved per row. Qdrant is removed because source fixed in#1181; CDSE remains
open despite partial source repair and four successful deployments in#1182.

Review depth is explicit:123 rows retain the old execution plan after current
registry reconciliation; one Arabic defect was independently reproduced; CDSE
source/evidence and scoped control-plane outcomes were rechecked; ten more rows
have control-plane-only updates. This is not135 independently reproduced defects.
The twelve operational update rows include Qdrant as a supplemental fixed-gap
followup outside the135. Current grouping is35 bounded next actions and100 whose
decisive next work depends on decisions/operations/external evidence; old37/99
was the136-plan grouping and is retained as history. Neither group is a closure
count or a replacement for existing user authorization.

Read `wave1_remaining_135_plan.json` with `wave1_remaining_135_coverage.json`.
`copy_manifest.json` records raw and copied hashes and link normalization.
No application, database, provider, backup, receipt-persistence or performance
probe was run by this plan refresh. CI/build/deployment success does not prove
the operational closing conditions. Original deadlines are historical inputs.

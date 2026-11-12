# Decision Lineage Knowledge Graph

> Static repository evidence only. This report does not prove runtime execution or production operation.

## Summary

- Stages: **10**
- Stages with repository evidence: **10**
- Static-supported relations: **9 / 9**
- Complete static chain: **yes**
- Runtime verified: **no**
- Production certified: **no**

## Stage coverage

| Order | Stage | Primary owner | Evidence files |
|---:|---|---|---:|
| 1 | `evidence` | `sahool-platform` | 687 |
| 2 | `candidate` | `sahool-platform` | 557 |
| 3 | `decision` | `sahool-platform` | 198 |
| 4 | `review` | `sahool-platform` | 304 |
| 5 | `plan` | `decision-service` | 49 |
| 6 | `authorization` | `sahool-platform` | 183 |
| 7 | `request` | `decision-service` | 40 |
| 8 | `receipt` | `decision-service` | 45 |
| 9 | `outcome` | `sahool-platform` | 57 |
| 10 | `learning` | `sahool-platform` | 342 |

## Remaining static gaps

No missing stage or unsupported adjacent relation was found by the static scanner.

## Certification boundary

A complete static chain means only that repository artifacts exist for each stage. Runtime verification requires correlated live identifiers, persisted records, telemetry, and execution receipts from a running stack.

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
| 1 | `evidence` | `sahool-platform` | 668 |
| 2 | `candidate` | `sahool-platform` | 536 |
| 3 | `decision` | `sahool-platform` | 187 |
| 4 | `review` | `sahool-platform` | 291 |
| 5 | `plan` | `decision-service` | 44 |
| 6 | `authorization` | `sahool-platform` | 171 |
| 7 | `request` | `decision-service` | 38 |
| 8 | `receipt` | `decision-service` | 43 |
| 9 | `outcome` | `sahool-platform` | 54 |
| 10 | `learning` | `sahool-platform` | 320 |

## Remaining static gaps

No missing stage or unsupported adjacent relation was found by the static scanner.

## Certification boundary

A complete static chain means only that repository artifacts exist for each stage. Runtime verification requires correlated live identifiers, persisted records, telemetry, and execution receipts from a running stack.

# SAHOOL Farmland Phase 2 — deliverables

Exported packages only; the source of truth is each wave's branch and PR. Not for direct production use.

| File | Wave | Source branch / PR | Head | Base | State |
|---|---|---|---|---|---|
| SAHOOL_Farmland_Phase2_ZIP01_wave1_80c86a88.zip | ZIP 01 — Wave 1 part (0001 standards & compliance, 0002 soil & land quality) | claude/farmland-phase2-wave1-20261125 / #1624 | 80c86a88 | main f834f4ec | **current**: merged to main as 5338b010 (tree equals the head); CI green, hospital PASS, lab 1624-v2 PASS |
| SAHOOL_Farmland_Phase2_ZIP01_wave1_b73d4e77.zip | same | same | b73d4e77 | main 7551198a | superseded: the hospital's delta review failed this head on a date-dependent test, fixed in 40dbf135 |

Verify: `sha256sum -c SHA256SUMS`, then inside the ZIP `sha256sum -c SHA256SUMS` and follow APPLY.md.
Wave 2 (Codex, #1621) is added to ZIP 01 after its engine is moved out of `shared/` and regenerated.

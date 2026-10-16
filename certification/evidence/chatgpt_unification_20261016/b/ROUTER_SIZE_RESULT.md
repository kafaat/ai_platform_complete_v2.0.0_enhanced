# Router size refactor

Base staged tree: badd7e5100fc3f36446e8e021510c0e25201f6d5. Isolated worktree irrigation-router-size; no shared edits, commit, or push.

irrigation_recommendation.py: 923→789 lines, below800. decision_review.py:947→921 lines, exactly existing frozen921 cap. No ceiling/baseline changes and no new modules.

Existing irrigation_models owns the unchanged request classes; route imports preserve exposed request names. Existing pure irrigation_engineering_workspace owns manual snapshot/coordinate/date validation and manual-plan parsing, while router maps ValueError to the same HTTP status/detail and retains DB transaction/INSERT ownership. Existing weather_service_client owns the unchanged field forecast adapter; the router wrapper explicitly passes its forecast_loader so existing mocking boundary remains intact. No formula, water defaults, authorization, or execution-policy changes.

Validation exact final source bytes in router-size-files.json:
- router-size-green.log:84 passed,0 skipped including23 manual source tests, native recommendation/review tests, engineering contracts, module count and entire router size ratchet.
- router-size-static.log:10 passed,0 skipped (depletion wiring, imagery/weather/irrigation workspace guard, weather client path contracts).
- Ruff check/format and git diff --check pass.
- Route ownership build_inventory passes with18 changed line anchors; identities/owners/count unchanged. Manual docs map included in patch; generated inventories left to root.
- Both existing weather_service_client mutation registry source anchors match exactly once (1,1). No mutation registry edits needed.
- No frontend changes, so no additional tsc run.
- git apply --check router-size.patch passes against shared integration tree.

Patch SHA256:8ea0d3f6a9bc62610703f114bdfdd1fb8ee3cf166a3e686d729d1ef590e1f0b0.

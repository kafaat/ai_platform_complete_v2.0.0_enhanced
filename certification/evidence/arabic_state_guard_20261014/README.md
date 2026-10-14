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

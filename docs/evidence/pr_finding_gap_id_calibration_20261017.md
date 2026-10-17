# pr_finding_gap_id_guard — calibration of the one-ID-per-finding rule (2026-10-17)

Gap: `GAP-REGISTRY-DOES-NOT-REQUIRE-IDS-FOR-PR-FINDINGS-01`, the two remaining parts left by
wave 4 (#1205): several findings in one paragraph passed with one ID, and GitHub review
comments were not read at all.

## What changed in the rule

* **Before** (`origin/main` @ `ec3927cef`): the unit was the paragraph. A labelled review
  paragraph passed if it named at least one registered gap ID.
* **After:** the unit is the **label occurrence**. A labelled review paragraph needs as many
  *distinct* registered IDs as it has labelled findings. Two label forms around the same
  severity word (`severity: **High**`, `Finding 3 (High)`) count once, because they share
  the word's position. Label forms, review-context words and the registry reader did not
  change.

## Measurement on history

Method: the guard's own `evaluate()` was run over every non-merge commit message. It was
run once with the guard from `origin/main` and once with the new guard, against the same
registry (744 registered IDs), and the two outputs were compared as sets.

| Corpus | Commits | Labelled paragraphs | …in review context | …with more than one label | Flags before | Flags after | New flags |
|---|---|---|---|---|---|---|---|
| `git log --no-merges 0e5281614` (wave-4 calibration base) | 2393 | 10 | 8 | 0 | 7 in 5 commits | 7 in 5 commits | 0 |
| `git log --no-merges origin/main` (`ec3927cef`) | 2395 | 10 | 8 | 0 | 7 in 5 commits | 7 in 5 commits | 0 |
| `git log --no-merges --remotes=origin` (615 refs) | 3674 | 13 | 10 | 0 | 9 in 7 commits | 9 in 7 commits | 0 |

**New flags under the counting rule: none.** There is nothing new to classify. The flags
are identical before and after, down to the label and first line reported.

The table also shows a limit. No commit in any of these corpora has a labelled review
paragraph with more than one label. So history neither confirms nor contradicts the
counting rule: it adds no false positive, but it is never exercised. The synthetic witnesses
in `tests_v9/test_pr_finding_gap_id_guard.py` are its only evidence:

* `test_two_findings_in_one_paragraph_need_two_ids` is accepted on `origin/main` and
  rejected now.
* `test_one_distinct_id_per_finding_is_the_remedy` shows the remedy passes.
* `test_label_forms_around_one_word_are_one_finding` shows the deduplication.

PR bodies were not measured. Reading them needs the GitHub API, which this session did not
use.

### The flags that exist both before and after

All of these were already flagged by the wave-4 guard. They are unchanged. Each is a
severity-labelled review or audit finding that names no registered ID, so each is a true
positive by the rule's definition, as classified in the wave-4 calibration.

| Commit | Label | Paragraph opens with | Class |
|---|---|---|---|
| `18b64ed0f` | `(High)` | `مراجعة Copilot (High) على #1122: …` | true positive (Copilot review finding) |
| `18b64ed0f` | `- High:` | `مراجعة #1130:` | true positive (review finding list) |
| `75b3ad5c8` | `Finding 2 (CRITICAL)` | `Finding 2 (CRITICAL) — raster-service silently wrote/read no data …` | true positive (diagnostic finding) |
| `75b3ad5c8` | `Finding 4 (HIGH)` | `Finding 4 (HIGH) — scout-ingest-projection crash-loop …` | true positive (diagnostic finding) |
| `203cabebb` | `- HIGH:` | `- HIGH: ValidatedRasterProduct rejected honest …` | true positive (review-verified gap) |
| `8a6d023af` | `(Critical)` | `- **V8-09 (Critical)** docker-compose.fixed.yml: …` | true positive (audit item, V8 ID not in the registry) |
| `63a1ad7fd` | `(High)` | `تدقيق خارجيّ (High): docker-compose.unified.yml …` | true positive (external audit) |
| `eb2633628` (off-main ref) | `- High:` | `مراجعة #1130:` | same paragraph as `18b64ed0f`, before the squash |
| `f35c1c6d6` (off-main ref) | `(High)` | `مراجعة Copilot (High) على #1122: …` | same paragraph as `18b64ed0f`, before the squash |

The three former false positives of the draft before wave 4 stay green under the new rule:

* `8722ea99`: a blocked substance `(CRITICAL)`.
* `79dae5e1`: approval tiers `LOW=0/MEDIUM=1/HIGH=2/CRITICAL=3`.
* `7c897ea1`: water-stress levels `WATCH · CRITICAL`.

The verbatim tests for these three pass.

## GitHub review comments

* **Fetch:** the `capability-registry` job (`.github/workflows/capability-governance.yml`)
  fetches `/pulls/<n>/comments` and `/pulls/<n>/reviews` on `pull_request` events. It reads
  100 items per page until a page is short, up to 30 pages, and writes every page's HTTP
  status and body to `/tmp/pr-reviews.json` (`sahool.pr-review-bodies.v1`).
* **Judge:** the guard judges that file through `--review-comments-file`.
* **Simulation:** the fetch step's `run:` script was run locally against a stand-in HTTP
  server for four cases:
  * two pages of comments: the full first page continued to a short second page, and both
    were read;
  * HTTP 403 on a same-repository PR: failed closed;
  * an HTML body with HTTP 200: read error, failed closed;
  * connection refused on a fork: reported as not measured, and skipped.

**Status: implemented but not measured live.** No real PR run has shown the fetch step
reading GitHub yet. The first PR that carries this change is that measurement. Until a run
log shows `HTTP 200 ← comments page 1` and the guard line
`… review comment(s) + … review(s) in … thread(s)`, this part should not be called closed.

Honesty limits:

* IDs are counted, not bound. The guard does not prove which ID answers which finding.
* Conversation-tab comments (`/issues/<n>/comments`) are not read.
* A review posted after the last workflow run is read only on the next push or edit of the
  PR.
* A fork whose token cannot read the comments is reported as not measured, not judged.

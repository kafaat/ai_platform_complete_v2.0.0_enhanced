# Evaluation results — UWRP Professional v4.2 (2026-10-19)

Adoption stage: **BEHAVIOR_EVALUATED (trigger layer only)**, on top of STATIC_VALIDATED. The step-following behaviour of each skill (does an agent that loaded it obey it?) is **not measured**; v4.1's 24 behavioural scenarios remain unexecuted.

## 1. Skill selection, blind (measured)

**Method.** `skill-evaluator/scripts/trigger_eval.py emit` built one prompt per description set: the 10 skill names and descriptions, then 36 tasks in one shuffled order (seed 1019). The tasks were 8 negatives where no skill should load, 6 in Arabic, and the rest drawn from v4.1's scenarios. Each prompt went to a fresh sub-agent that saw only that file. Replies were scored with `trigger_eval.py score`.

**Sets.**
- **A:** v4.1 descriptions as shipped, 204–234 characters.
- **B:** v4.2 descriptions, 175–189 characters, each with when to use and when not to.
- **C:** B plus 184- and 188-character upload variants of the two frozen baselines, whose shipped descriptions are 308 characters.

| Set | Claude (session default model) | Claude Haiku | False triggers on negatives |
|---|---|---|---|
| A: v4.1 | 35/36 | 36/36 | 0/8 and 0/8 |
| B: v4.2 | 36/36 | 36/36 | 0/8 and 0/8 |
| C: v4.2 + upload baselines | 36/36 | 36/36 | 0/8 and 0/8 |

The one miss: in set A with the default model, EVAL-02 (adopt a skill that contains `curl | bash`) also loaded `change-review`.

**Reading.**
- The shorter descriptions route as well as the longer ones; no loss was measured.
- They are not shown to be *better*: v4.1 already sat at the ceiling, and a one-case difference is noise at n = 1 per cell.
- The real gain is portability. Every v4.1 description, and both baselines (308 characters), exceeds the 200-character claude.ai upload limit.
- The scenario set is easy, since most prompts name their domain. A harder, ambiguous set is the next measurement to run.

**Limits.**
- One reply per cell; two Claude models; one prompt wording.
- Sub-agents run inside Claude Code, and their own context may list other skills; they were told to judge only from the file.
- Not run on Codex, Kimi or OpenCode. `trigger_eval.py emit` produces a prompt any of them can answer, and `score` grades it.

**Receipts** (first 16 hex digits of SHA-256):
- scenarios `be1e08e6a16b1eb8`
- description sets `5008a2602a1ab69b`
- prompts A `fcd812328f28efa1`, B `13c89f86a8e8c83b`, C `d87cdf805a9cea10`
- receipt list over the prompts and the six replies: `7adbf328d4584cd4`

## 2. Defects found in v4.1 and fixed here (measured on the owner's archive `2e178008…`)

1. `scripts/validate_pack.py` fails the intact v4.1 package. The membership is identical; only the order differs, because it sorts `Path` objects while `SHA256SUMS` is sorted as strings. `verify_pack.py` passed the same tree, and the 27 tests call only `verify_pack`. Fixed with one verifier that sorts posix strings.
2. Skills were not self-contained. `work-router` pointed at `templates/` and `baselines/*.zip` outside its folder, and `evidence-research` pointed at `research/SOURCE_REGISTER.json`, so installing one skill alone broke its references. Each skill now carries its own `assets/`, and the verifier rejects any link that leaves its skill folder.
3. All 10 descriptions exceed claude.ai's 200-character limit (204–308). Fixed for the 8 managed skills. The two frozen baselines keep their bytes; upload variants change only the description line.
4. `skill-evaluator` requires "Use when / Do not use when" in descriptions; none of the 8 had a negative clause. Fixed.
5. The routing rules existed twice, in the `work-router` text and hard-coded in `route_work.py`. Moved to `references/routing.json`, read by the script and cross-checked against the text by the verifier.
6. `CHANGELOG.md` carried two `v4.1.0` headings.

## 3. Static checks (measured)

`verify_pack.py` PASS; `agentskills validate` (skills-ref 0.1.1) valid for each of the 8 skills; the package unit tests pass. Counts are in the PR or release note that ships this version, tied to its commit.

## 4. Not measured

Step compliance of any skill; time or cost savings; behaviour on non-Claude agents; the claude.ai upload itself (only the documented constraints were checked); multi-agent coordination under real contention.

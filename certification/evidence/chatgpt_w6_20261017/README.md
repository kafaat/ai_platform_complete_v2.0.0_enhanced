# W6 — one evidenced closure, six-closure target not yet met

Base: `2eab1348d6106555b4ab823c2fd194db1d105f7e` (#1207).
Source fix: `4d0799f32c714a87c7840f35232da42d18cbc2b1`.
Scope: the owner's follow-up asks to close six remaining gaps outside Claude's work,
in one PR. It does not revoke the named migration/GATE-01/deployment/design limits.
This pack establishes **one** source closure; it does not claim six.

## SAM2-REF-FLOATS-ON-MAIN-AND-WEIGHTS-UNVERIFIED-01

The source pin already exists at `services/sam2-inference/Dockerfile:43`.
W5 measured the official checkpoint bytes, but both provisioning guides still
performed an unchecked download. The new operator entry point
`scripts/ops/provision_sam2_checkpoint.py:20-24` binds the existing default model
to its official URL, published SHA256 and measured size. There is no URL/digest
CLI override. `:45-71` downloads to a temporary file and checks its stored bytes
before replacing the final path. Failed downloads preserve existing weights.
`--check` (`:74-91`) rehashes an existing file without network or service changes.
The runtime independently verifies mounted bytes before Torch
(`services/sam2-inference/sam2_runtime.py:109-160`), unchanged in this PR.

Both `sam2-models/README.md:11` and `docs/SAM2_DEPLOYMENT.md:55` now use this
entry point and the exact digest. The deployment guide now describes the actual
read-only bind mount instead of an unrelated named volume. It no longer points
to the retired fixed Compose stack. No Compose/env/runtime file was changed.

### Reproduction and raw results

```bash
python scripts/ops/provision_sam2_checkpoint.py --output-dir /tmp/sahool-w6-checkpoint-proof
python scripts/ops/provision_sam2_checkpoint.py --output-dir /tmp/sahool-w6-checkpoint-proof --check
python -m pytest -q tests_v9/test_sam2_artifact_digest.py tests_v9/test_sam2_ref_pinned.py
```

- `sam2/provision.json`: actual official Meta download through the new entry point,
  897952466 bytes, SHA256
  `7442e4e9b732a508f80e141e7c2913437a3610ee0c77381a66658c3a445df87b`.
- `sam2/recheck.json`: independent disk rehash by `--check` on the saved file.
  Its `status=verified` is a **byte-check result**, not a gap-state promotion.
- `sam2/unit.xml` and `sam2/unit.log`: 28 passed, no skips (13 new cases).
  `tests_v9/test_sam2_artifact_digest.py:258-360` checks the publisher pin,
  atomic publication, wrong digest, truncation, oversize, interrupted read and
  HTTP rejection with/without an installed file, plus offline rechecking.
- `sam2/mutation-results.json` and the three named logs: 3/3 isolated mutants
  rejected (digest comparison removed, size comparison removed, publication
  moved ahead of verification). Each targets two cases and returns pytest 1.
- `sam2/initial-mutation-results.json` records an initial weakness in the tests:
  removing the size comparison survived because the digest comparison still
  rejected truncated data. The final tests assert the specific rejection reason;
  the size mutant now fails too. No surviving mutant is reported as killed.

### Acceptance boundary

| Level | Result |
|---|---|
| Local source/provisioning | Measured official download, stored-byte recheck, 28 passing tests, 3 killed mutants. This meets the gap's source pin + measured digest + enforced download condition. |
| Staging | Not provisioned or exercised. No mounted checkpoint/image/config receipt or GPU inference acceptance. |
| Production | Not provisioned or exercised. No deployment, runtime attestation, inference quality or production certification claim. |

The weights were written only under the isolated `/tmp` test path, not the GPU
service mount. No Torch deserialization occurred. `fixed` describes this source
repair in the PR; no `verified` promotion. Main gains it only after owner-approved
merge of the final head.

## Why other readily suggested closures are still open

These are concrete remaining conditions, not requests to repeat landed code.
References below are line numbers on the pinned base above.

| Gap | Remaining condition; next permitted work |
|---|---|
| `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01` | `sahool-brain/gaps/registry.md:104`: W5 already delivered seven behavioral tests and three mutants. The live-import/general semantic class is unproved; another string-search guard cannot close it. |
| `JWT-DECODE-OUTSIDE-SHARED-SECURITY-01` | `sahool-brain/gaps/registry.md:6237`: only actuator remains; `docs/architecture/gate01_policy.json:35` freezes its runtime. No second vegetation/MCP migration is needed. |
| `MIGRATOR-SCRIPT-DEFAULT-ROLE-PASSWORDS-01` | `sahool-brain/gaps/registry.md:7373-7376`: code and guard landed in #1170. Owner configuration/run receipts remain; no reason to edit migrations again. |
| `PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01` | `sahool-brain/gaps/registry.md:5892`: artifact transfer, attestation and GUARDS producer were repaired. Missing live guard runs and deployment provisioning evidence cannot be fabricated by changing CI. |
| `ROUTER-SIZE-UNGUARDED-AFTER-MAIN-DECOMPOSITION-01` | `sahool-brain/gaps/registry.md:6238`: the size ratchet exists and is enforced. Extraction requires the owner's agreed plan and coordinated guard/map changes; no automatic split. |
| `OWNER-AUDIT-20260920-FINDINGS-LIVE-OUTSIDE-THE-TRACKED-REGISTRY-01` | `sahool-brain/gaps/registry.md:206`: much of F-GLOBAL is mapped, but the original complete thirteen-result audit is not present. In particular a definition of F-GLOBAL-13 was not recovered from tracked docs/brain. A made-up mapping would not satisfy the tracking condition. |
| `AUDIT-FINDINGS-NAMED-BUT-NOT-YET-MEASURED-BY-ME-01` | `sahool-brain/gaps/registry.md:228`: actual measurements of the named ten-field satellite sample, safe approval sandbox and intersecting boundary rejection are required. No substitution of unrelated fixtures for the original sample. |
| `REPORT3-RAG-02/05/06/08/12-01` | `sahool-brain/gaps/registry.md:6440-6449`: W5's current-stack baseline is blocked by absent Qdrant/Ollama; its historical BM25 result is not the missing baseline. Prefix/reseed/model changes remain prohibited before that measurement and owner decision. |
| `TTS-PIPER-KAREEM-DATASET-HAS-NO-LICENSE-01` | `sahool-brain/gaps/registry.md:6932-6935`: publisher dataset authorization or an owner-selected replacement is still required. Public availability of the repository does not supply that receipt. |
| `TTS-SILMA-WEIGHTS-LINEAGE-UNVERIFIED-01` | `sahool-brain/gaps/registry.md:6967-6970`: the publisher still describes public/proprietary training data without the specific source confirmation required by this gap. The advertised model license alone is not that confirmation. |

Publisher pages re-read on 2026-10-17:
https://github.com/AliMokhammad/arabicttstrain and
https://huggingface.co/silma-ai/silma-tts (model details/training/license).
No publisher was contacted and no licensing approval was inferred.

`open-gaps-at-base.json` retains all 88 canonical open IDs with their registry
source locations, using `gap_registry_measure.measure` classification, excluding
historical/alias/policy entries. Base counts: 440 fixed, 88 open, 3 verified.
Claude's six IDs (Redis, learning, PR findings, edges, ownership, connectivity)
remain assigned to Claude even though the open-PR API returned an empty list.
The protected file boundaries, migration freeze and GATE-01 remain unchanged.

---
name: experience-collector
description: "Use when documenting lessons from verified work or recurring failures for future skill improvements. Not for raw logs, automatic rule changes or secret collection."
metadata:
  version: "4.3.0"
  package: uwrp-professional
---
# Experience Collector — evidence first, no self-training

Record *bounded, redacted* observations from completed or interrupted work so future improvements can be proposed without relying on agent memory. Independent of model, project, operating system and hosting provider.

1. Identify the real outcome, the installed skill version/digest, the event category and a reference to primary evidence. A reported lesson is **not** verified merely because it is recorded.
2. Sanitize **before ingestion**, minimize identifiers, and never store raw prompts, personal data, credentials, unrestricted logs, attachments or proprietary source text. The bundled scanner detects only selected secret patterns, not every sensitive value. Follow the applicable institutional data policy.
3. Record one observation using a stable ID, a skill digest and an evidence digest. Duplicates with identical content are idempotent; conflicting reuse of IDs is rejected.
4. Use the local journal only in an **authorized scratch location**, not a checkout with immutable tree gates. The journal is an append-only hash chain; its local lock is *not* a distributed lock. The optional checkpoint can be rebuilt from journal evidence.
5. Treat every journal entry as `RECORDED_UNVERIFIED`. Inspect original sources independently before promoting a claim or applying an improvement. Verify chain integrity after an interruption; never truncate automatically.
6. Publish only a small, reviewed summary/manifest to authorized persistent storage. Do not auto-upload logs or assert that local storage survives a container restart.

**Optional offline tool:** `python3 scripts/experience_journal.py record --input assets/observation.example.json --journal /authorized/scratch/experiences.jsonl`. This writes locally only; review the input and destination first. `verify` and `summary` are read-only.

See [Data and retention policy](references/DATA_POLICY.md) and [example observation](assets/observation.example.json). This skill grants no permission for push, merge, deploy, delete, upload, or modifying any Skill.

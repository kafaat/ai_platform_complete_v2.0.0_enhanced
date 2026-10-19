---
name: failure-investigation
description: "Root cause with a fails-before, passes-after witness. Use when a test, build or service failure has an unknown cause, is intermittent, or a fix already failed. Not for known one-line fixes."
metadata:
  version: "4.2.0"
  package: uwrp-professional
---
# Root-cause investigation

**Use when** a test, build, service or document failure has an unknown cause, is intermittent, or a previous fix failed. **Skip** for a known, obvious one-line fix.

1. Separate symptom, environment, time, version, input and first hypothesis. Keep the original error evidence, without secrets.
2. Find the smallest safe reproduction. Compare against a working baseline and recent changes. For intermittent failures, separate flakiness, resource exhaustion and deterministic regressions; measure, do not re-run until green.
3. Write competing hypotheses, each with a discriminating probe. Change one variable at a time. Read-only probes first on hazardous systems.
4. Name the failing contract and why it fails. Keep a **negative witness** that fails before the fix, apply the smallest authorized correction, then run the same witness after it.
5. Widen tests by impact and run the mandatory gates. If the fix fails, reopen the investigation; no serial speculative edits.
6. Record `failure → evidence → cause (confidence) → correction → regression` with exact versions ([`assets/verification-receipt.example.json`](assets/verification-receipt.example.json)). A passing targeted test is not deployment acceptance.

Pattern adapted from Superpowers systematic debugging, without its blanket rules.

**Authority boundary:** this skill grants no permission to push, merge, deploy, delete, upload or bypass project rules. The user's instructions and project policy win.

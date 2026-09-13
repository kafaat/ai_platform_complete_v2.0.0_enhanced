# Pending physical-effect patch

`SUP-08-actuator-v2-PENDING-GATE-01.patch` is a review artifact only. The actuator
runtime and ESP32 firmware remain unchanged in the applied repair series.
`git apply --check` verifies that the proposal matches the source; it does not
apply the change or prove its physical behavior.

`docs/architecture/gate01_policy.json` keeps GATE-01 **CLOSED**. A generic repair
request does not supply the independently adjudicated authorization bound to
exact proposed bytes required by that policy. The adjacent manifest records the
before/proposed source hashes and patch digest so the owner can review a concrete
scope. No policy, frozen baseline, or adjudication was changed by this work.

The proposal binds the command, tenant, device, payload, stable request ID and
expiry to one signed body. It derives a device key from the server root and
includes a firmware verifier and persistent intent/completion records in NVS.
Uncertain work after a power failure is not automatically repeated. Signed
receipts identify relay output; they do not claim water delivery or valve position.

This proposal is **not ready for production application**. It requires owner
adjudication, review of legacy rule and compensation callers, durable receipt
ingestion/reconciliation, device clock and key provisioning, ESP32 compilation,
NVS capacity/power-loss tests, transport tests, and a coordinated v2 cutover.
The old wire format is rejected by the proposed firmware, and callers without a
durable bound ID are rejected by the proposed server. Those effects must be part
of the approval and rollout plan. SUP-08 remains open.

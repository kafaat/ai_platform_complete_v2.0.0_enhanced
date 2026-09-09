# Edge Inference model provisioning

The edge-inference service is intentionally fail-closed. The repository does not ship pest or yield ONNX weights. Operators must mount the model volume at `/models` and provide:

- `/models/pest_detector_int8.onnx`
- `/models/yield_estimator_int8.onnx`

The service exposes `/capabilities` and `/readyz` so deployment automation can see whether those contracts are active.

Recommended production mode:

```env
EDGE_READINESS_MODE=strict
PEST_MODEL_PATH=/models/pest_detector_int8.onnx
YIELD_MODEL_PATH=/models/yield_estimator_int8.onnx
PEST_MODEL_SHA256=<64-hex sha256 of the approved pest weight>
YIELD_MODEL_SHA256=<64-hex sha256 of the approved yield weight>
```

**A file name never activates a capability.** `/capabilities`, `/readyz`, `download_models.py`
and the two inference endpoints all verify the mounted bytes against the configured SHA-256 and
stay fail-closed on a missing, malformed or mismatched digest (`reason` names which). The approved
model record must separately pin model/version, license, class taxonomy, training-data provenance
and regional calibration evidence **before** a digest is set — the digest proves identity, not fitness.

**The detector is observation-only.** Detections carry class, confidence, bbox, affected crops and
severity, with `action_policy: observation_only`. No treatment or pesticide is emitted by the
detector; agronomic action requires a policy layer and an approved diagnosis.

Use `EDGE_READINESS_MODE=partial` only when Edge inference is optional and endpoint-level 503 responses are acceptable until models are provisioned.

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
```

Use `EDGE_READINESS_MODE=partial` only when Edge inference is optional and endpoint-level 503 responses are acceptable until models are provisioned.

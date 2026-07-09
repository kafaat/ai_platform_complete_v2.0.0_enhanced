# Edge Model Provisioning Checklist

Edge inference is intentionally fail-closed until operators provision real ONNX models.
Do not commit model binaries into the repository.

Required runtime files:

- `/models/pest_detector_int8.onnx`
- `/models/yield_estimator_int8.onnx`

Required runtime policy:

- Development/demo without models: `EDGE_READINESS_MODE=partial`, `EDGE_PRODUCTION_REQUIRED=false`
- Production where Edge is sold/enabled: `EDGE_PRODUCTION_REQUIRED=true`

Expected behavior:

- Missing models in partial mode: `/readyz` returns 200 with `status=degraded`.
- Missing models in strict/production-required mode: `/readyz` returns 503 with `status=degraded`.
- Inference routes return 503 rather than synthetic detections or fabricated yield estimates.

Verification:

```bash
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
python scripts/ci/production_honesty_guard.py
```

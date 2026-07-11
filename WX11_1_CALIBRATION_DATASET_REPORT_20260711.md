# WX-11.1 Calibration Dataset Boundary

Implemented an authoritative, tenant-scoped, read-only calibration dataset over immutable learning attributions and verified outcomes.

- `GET /v1/learning/calibration-dataset`
- `GET /api/v1/learning/calibration-dataset`
- Filters by `model_id` and nullable `feature_set_id`
- Returns lineage, labels, weights, evidence snapshots, outcome metrics, and weighted success rate
- Fails closed outside Decision-Service SoR mode
- Performs no fitting, optimizer update, registry promotion, redispatch, or actuation

This is the dataset/read boundary only. Candidate training and governed promotion remain later WX-11 increments.

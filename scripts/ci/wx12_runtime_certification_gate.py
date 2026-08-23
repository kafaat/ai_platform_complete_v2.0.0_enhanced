from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = [
    "services/model-registry-adapter/adapter.py",
    "services/model-registry-adapter/worker.py",
    "scripts/wx12/postgres_certification.py",
    "scripts/wx12/staging_activation_rollback_drill.py",
    "certification/wx12/WX12_CERTIFICATION_MATRIX.md",
    "docs/runbooks/WX12_RUNTIME_PRODUCTION_CERTIFICATION.md",
    ".github/workflows/wx12-runtime-certification.yml",
]
missing = [p for p in required if not (ROOT / p).exists()]
if missing:
    raise SystemExit(f"WX-12 gate missing: {missing}")
text = (ROOT / "services/model-registry-adapter/adapter.py").read_text(encoding="utf-8")
for token in ["compare_and_swap", "MODEL_REGISTRY_DRY_RUN", "SAHOOL_ENV", "MODEL_REGISTRY_TOKEN"]:
    if token not in text:
        raise SystemExit(f"WX-12 gate missing token: {token}")
print("wx12_runtime_certification_gate: PASS")

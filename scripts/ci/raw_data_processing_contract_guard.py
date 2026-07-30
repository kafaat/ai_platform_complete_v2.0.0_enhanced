#!/usr/bin/env python3
"""Guard the raw raster data processing contract.

The raw-data path must remain an explicit QA/provenance endpoint in
raster-service, not hidden in main.py and not confused with fabricated indicator
computation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def build_payload() -> dict:
    errors: list[str] = []
    models = _read("services/raster-service/raster_api_models.py")
    runtime = _read("services/raster-service/raster_processing_runtime.py")
    raw = _read("services/raster-service/raw_data_processing.py")
    router = _read("services/raster-service/routers/processing.py")
    main = _read("services/raster-service/main.py")

    required = {
        "RawDataProcessRequest model": "class RawDataProcessRequest" in models,
        "RawDataProcessResponse model": "class RawDataProcessResponse" in models,
        "raw runtime module": "def process_raw_raster" in raw,
        "runtime adapter": "raw_data_processing.process_raw_raster" in runtime,
        "raw endpoint": '@router.post("/raw/process")' in router,
        "service-token guard": "require_service_token" in router and "process_raw_data" in router,
        "no raw logic in main": "raw_data_processing" not in main and "/raw/process" not in main,
        "no fabricated indicator": "fabricated_indicator" in raw and "indicator_computed" in raw,
        "bounded sampling": "max_pixels" in raw and "sampled_every_" in raw,
    }
    for name, ok in required.items():
        if not ok:
            errors.append(name)

    status = "ok" if not errors else "failed"
    payload = {
        "schema": "sahool.raw_data_processing_contract/1",
        "status": status,
        "errors": errors,
        "endpoint": "POST /raw/process",
        "owner": "services/raster-service/raw_data_processing.py",
    }
    if errors:
        raise SystemExit("raw_data_processing_contract_failed: " + ", ".join(errors))
    print("raw_data_processing_contract_ok")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output = ROOT / "raw_data_processing_contract.generated.json"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != rendered:
            print("raw_data_processing_contract drift; rerun without --check")
            return 1
    else:
        output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""S5 end-state witness: imagery-provider authority is not duplicated in sahool-platform."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]

def test_platform_imagery_registry_is_retired():
    assert not (ROOT/"services/sahool-platform/api/imagery_providers.py").exists()

def test_imagery_runtime_is_owned_by_raster_service():
    cdse = ROOT/"services/raster-service/cdse_client.py"
    gate = ROOT/"services/raster-service/imagery_source_gate.py"
    assert cdse.is_file() and gate.is_file()
    src = cdse.read_text(encoding="utf-8")
    gate_src = gate.read_text(encoding="utf-8")
    assert "class CdseClient" in src
    assert "def is_configured" in src
    assert "PRIMARY_SOURCE" in gate_src and "FALLBACK_SOURCE" in gate_src

def test_no_production_import_of_retired_imagery_registry():
    offenders=[]
    for p in sorted((ROOT/"services").rglob("*.py")):
        rel=p.relative_to(ROOT).as_posix()
        if "/tests/" in rel or p.name.startswith("test_"):
            continue
        txt=p.read_text(encoding="utf-8",errors="ignore")
        if re.search(r"api\.imagery_providers|imagery_providers",txt):
            offenders.append(rel)
    assert offenders == []

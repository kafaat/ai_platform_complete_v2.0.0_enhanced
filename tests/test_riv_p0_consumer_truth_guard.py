import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _literal_return(path: Path, function_name: str) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function_name
    )
    returned = next(item for item in ast.walk(node) if isinstance(item, ast.Return))
    value = ast.literal_eval(returned.value)
    assert isinstance(value, dict)
    return value


def test_frontend_does_not_present_contract_service_as_compute_owner():
    files = [
        ROOT / "frontend/src/sections/DashboardPage.tsx",
        ROOT / "frontend/src/sections/SettingsPage.tsx",
        ROOT / "frontend/src/services/api/client.ts",
    ]
    text = "\n".join(p.read_text(encoding="utf-8") for p in files)
    assert "33 مؤشر + WOFOST" not in text
    assert "جارٍ تحميل البيانات من indicators-service" not in text
    assert "ownership/catalog contract only" in text


def test_legacy_direct_sentinel_path_is_removed_and_fail_closed():
    path = ROOT / "sentinel_hub/vegetation_real.py"
    text = path.read_text(encoding="utf-8")
    ready = _literal_return(path, "readyz")
    assert ready["runtime_role"] == "compatibility-only"
    assert ready["direct_provider_fetch"] is False
    assert "raster-service is the production owner" in text
    assert "EVALSCRIPT_ALL_INDICES" not in text
    assert "evaluatePixel" not in text
    assert "services.sentinel-hub.com" not in text
    assert "direct Sentinel-Hub computation was removed" in text

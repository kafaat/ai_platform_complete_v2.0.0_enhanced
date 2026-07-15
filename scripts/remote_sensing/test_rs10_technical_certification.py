import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).with_name("rs10_technical_certification.py")
spec = importlib.util.spec_from_file_location("rs10_cert", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_requires_five_fields(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"fields": [{"tenant_id": "t", "field_id": "f", "season_id": "s"}]}))
    result = mod.validate_manifest(p)
    assert result["manifest_valid"] is False
    assert result["agronomic_certified"] is False


def test_valid_manifest_is_technical_only(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(
        json.dumps(
            {
                "fields": [
                    {"tenant_id": f"t{i}", "field_id": f"f{i}", "season_id": f"s{i}"}
                    for i in range(5)
                ]
            }
        )
    )
    result = mod.validate_manifest(p)
    assert result["manifest_valid"] is True
    assert result["certification_scope"] == "technical_e2e_only"
    assert result["model_promotion_certified"] is False

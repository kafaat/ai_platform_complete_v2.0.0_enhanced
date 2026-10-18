"""The TiTiler parity harness must compare what SAHOOL sends, and report every difference."""

import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "titiler_parity", ROOT / "scripts/diagnostics/titiler_parity.py"
)
parity = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parity  # dataclasses resolve their module by name
spec.loader.exec_module(parity)


def png(array) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.asarray(array, dtype=np.uint8), "RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def solid(value=(10, 20, 30, 255), size=4):
    return np.tile(np.array(value, dtype=np.uint8), (size, size, 1))


def test_matrix_follows_the_only_sahool_caller():
    """If cog_tile_proxy changes its path or parameters, the matrix must change with it."""
    source = (ROOT / "shared/gis/cog_tile_proxy.py").read_text(encoding="utf-8")
    assert parity.SAHOOL_TILE_PATH in source
    sent = set(re.findall(r'params\["(\w+)"\]', source)) | set(
        re.findall(r'params = \{"(\w+)"', source)
    )
    assert sent == set(parity.SAHOOL_TILE_PARAMS)
    matrix = parity.request_matrix("-1,1")
    used = {key for case in matrix if case.path == parity.SAHOOL_TILE_PATH for key in case.params}
    assert used | {"url"} == set(parity.SAHOOL_TILE_PARAMS)


def test_every_case_names_its_caller_or_says_it_has_none():
    for case in parity.request_matrix("0,1"):
        assert case.used_by.strip()
        assert case.kind in {"png", "json", "stats", "status"}


def test_identical_png_is_identical():
    data = png(solid())
    assert parity.compare_png(data, data)["verdict"] == "identical"


def test_one_pixel_change_is_reported_with_its_size():
    left = solid()
    right = left.copy()
    right[0, 0] = (10, 20, 31, 0)
    detail = parity.compare_png(png(left), png(right))
    assert detail["verdict"] == "pixels_differ"
    assert detail["differing_pixels"] == 1
    assert detail["alpha_differing_pixels"] == 1
    assert detail["max_abs_diff"] == 255


def test_non_png_and_shape_changes_are_not_called_identical():
    assert parity.compare_png(b"{}", png(solid()))["verdict"] == "not_png"
    assert parity.compare_png(png(solid(size=4)), png(solid(size=8)))["verdict"] == "shape_differs"


def test_status_difference_wins_over_body():
    case = parity.request_matrix("0,1")[0]
    body = png(solid())
    row = parity.compare_case(case, (500, "application/json", b"{}"), (200, "image/png", body))
    assert row["verdict"] == "status_differs"
    assert row["a"]["status"] == 500 and row["b"]["status"] == 200


def test_same_failure_is_not_reported_as_parity_of_content():
    case = parity.request_matrix("0,1")[0]
    row = parity.compare_case(
        case, (404, "application/json", b"{}"), (404, "application/json", b"{}")
    )
    assert row["verdict"] == "same_non_200"


def test_info_reports_keys_on_one_side_and_changed_values():
    detail = parity.compare_json(
        {"bounds": [1, 2, 3, 4], "minzoom": 10, "dtype": "uint8"},
        {"bounds": [5, 6, 7, 8], "crs": "EPSG:32638", "dtype": "uint8"},
    )
    assert detail["verdict"] == "differs"
    assert detail["only_a"] == ["minzoom"] and detail["only_b"] == ["crs"]
    assert set(detail["changed"]) == {"bounds"}


def test_statistics_within_tolerance_match_and_beyond_it_do_not():
    a = {"b1": {"min": 0.1, "max": 0.9, "mean": 0.5}}
    assert (
        parity.compare_stats(a, {"b1": {"min": 0.1, "max": 0.9, "mean": 0.5 + 1e-12}})["verdict"]
        == "identical"
    )
    detail = parity.compare_stats(a, {"b1": {"min": 0.1, "max": 0.9, "mean": 0.6}})
    assert detail["verdict"] == "differs" and "b1.mean" in detail["differences"]
    assert parity.compare_stats(a, {"b2": a["b1"]})["verdict"] == "differs"


def test_report_keeps_hashes_not_bodies():
    case = parity.request_matrix("0,1")[6]
    body = json.dumps({"bounds": [1, 2, 3, 4]}).encode()
    row = parity.compare_case(
        case, (200, "application/json", body), (200, "application/json", body)
    )
    assert row["verdict"] == "identical"
    assert "bounds" not in json.dumps(row["a"])
    assert len(row["a"]["sha256"]) == 64

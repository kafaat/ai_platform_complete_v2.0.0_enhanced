"""Legacy Element84 remains contained; calibrated C1 has one guarded VRT path.

These tests run without rasterio in the minimal Unit Tests environment. They
inventory production entry points and execute the real C1 gate with traps at the
GDAL/processing boundary. Real TIFF calibration and entry-point side effects are
covered by raster-service/test_stac_c1_processing.py and
raster-service/test_element84_vrt_containment_runtime.py.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"


def _containment():
    spec = importlib.util.spec_from_file_location(
        "_radiometry_containment", RASTER / "radiometry_containment.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_rejection_is_structured_permanent_and_names_its_causes():
    rc = _containment()
    detail = rc.element84_vrt_detail(["red", "nir", "swir1", "scl"], entry_point="probe")

    assert detail["code"] == "radiometry_unresolved"
    assert detail["provider"] == "element84" and detail["path"] == "stac_vrt"
    assert detail["retryable"] is False
    codes = [r["code"] for r in detail["reasons"]]
    assert codes == [
        "reflectance_scale_unresolved",
        "band_grid_misaligned",
        "nodata_not_propagated",
    ]
    misaligned = next(r for r in detail["reasons"] if r["code"] == "band_grid_misaligned")
    assert misaligned["bands"] == ["swir1", "scl"]
    assert set(detail["gap_ids"]) == set(rc.GAP_IDS)


def test_alignment_is_claimed_only_when_a_twenty_metre_band_is_requested():
    """السببُ وقائعُ الطلب: red/nir وحدهما (10م) لا يحملان سبب المحاذاة — المقياس وNoData يكفيان."""
    rc = _containment()
    detail = rc.element84_vrt_detail({"red": "r", "nir": "n"}, entry_point="probe")
    codes = [r["code"] for r in detail["reasons"]]
    assert codes == ["reflectance_scale_unresolved", "nodata_not_propagated"]


def test_the_payload_carries_band_names_never_hrefs():
    """الحمولة تصل إلى العميل وإلى عمود المهمّة؛ الروابط (قد تحمل توقيعاً) لا تُعاد."""
    rc = _containment()
    hrefs = {"red": "https://signed.example/red.tif?X-Amz-Signature=abc", "nir": "s3://b/nir.tif"}
    with pytest.raises(rc.RadiometryUnresolved) as info:
        rc.reject_element84_vrt(hrefs.keys(), entry_point="probe")
    dumped = json.dumps(info.value.detail)
    assert info.value.detail["bands"] == ["nir", "red"]
    assert "https://" not in dumped and "s3://" not in dumped and "Signature" not in dumped


def test_the_item_error_prefix_is_the_permanent_marker_the_requeue_reads():
    rc = _containment()
    assert rc.ITEM_ERROR.startswith(rc.RADIOMETRY_UNRESOLVED + ":")


# One measured C1 boundary; legacy inputs remain rejected before raster I/O.


def _production_sources() -> list[Path]:
    out = []
    for path in sorted((ROOT / "services").rglob("*.py")):
        name = path.name
        if name.startswith("test_") or "tests" in path.parts or name == "stac_vrt.py":
            continue
        out.append(path)
    return out


def _calls(tree: ast.AST, attr: str) -> list[ast.Call]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name == attr:
                found.append(node)
    return found


def test_only_the_validated_c1_boundary_can_build_a_production_vrt():
    callers = []
    for path in _production_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for _call in _calls(tree, "build_band_vrt"):
            callers.append(str(path.relative_to(ROOT)))
    assert callers == ["services/raster-service/stac_c1_processing.py"], (
        "Every VRT entry must pass the validated C1 boundary",
        callers,
    )


ENTRY_POINTS = {
    ("services/raster-service/routers/fields.py", "process_from_stac"): "process_from_stac",
    (
        "services/raster-service/routers/fields.py",
        "field_historical_backfill",
    ): "historical_backfill",
    (
        "services/raster-service/backfill_scan_worker.py",
        "_process_scene_index",
    ): "backfill_scan_worker",
}


@pytest.mark.parametrize("rel,func", sorted(ENTRY_POINTS))
def test_each_entry_point_routes_through_the_same_c1_gate(rel, func):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == func
    )
    assert not _calls(fn, "build_band_vrt"), "Direct VRT construction bypasses C1 admission"
    calls = _calls(fn, "process_c1_scene")
    assert len(calls) == 1
    imports = [n for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)]
    assert any(
        n.module == "stac_c1_processing" and any(a.name == "process_c1_scene" for a in n.names)
        for n in imports
    )
    keywords = {kw.arg: kw.value for kw in calls[0].keywords}
    assert ast.literal_eval(keywords["entry_point"]) == ENTRY_POINTS[(rel, func)]
    assert "run_processing" in keywords


@pytest.fixture
def c1_boundary(monkeypatch):
    # Execute production gate functions unchanged, replacing only imported I/O
    # collaborators so these witnesses do not require GDAL or provider access.
    tree = ast.parse((RASTER / "stac_c1_processing.py").read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.Import)
            and any(
                alias.name in {"radiometry_containment", "raster_api_models", "stac_search"}
                for alias in node.names
            )
        )
    ]
    rc = _containment()
    models = types.SimpleNamespace(
        ProcessRequest=lambda **kw: types.SimpleNamespace(**kw),
        IndicatorKind=lambda value: value,
        SourceFormat=types.SimpleNamespace(sentinel2_l2a="sentinel2_l2a"),
        BandMapping=lambda **kw: kw,
    )
    namespace = {
        "radiometry_containment": rc,
        "models": models,
        "stac_search": types.SimpleNamespace(
            band_urls_from_assets=lambda assets: {
                key: asset["href"] for key, asset in assets.items()
            }
        ),
    }
    exec(compile(tree, str(RASTER / "stac_c1_processing.py"), "exec"), namespace)
    boundary = types.SimpleNamespace(**namespace)
    calls = []
    vrt = types.ModuleType("stac_vrt")

    def build(hrefs, directory, **kwargs):
        calls.append((hrefs, directory, kwargs))
        return str(Path(directory) / "stack.vrt"), {name: i for i, name in enumerate(hrefs, 1)}

    vrt.build_band_vrt = build
    monkeypatch.setitem(sys.modules, "stac_vrt", vrt)
    return boundary, rc, calls


@pytest.fixture
def c1_scene(c1_boundary):
    c1, _, _ = c1_boundary
    identity = "S2A_T38QND_20261015T073428_L2A"
    captured = "2026-10-15T07:34:28Z"
    assets = {}
    for name, band in c1.BANDS.items():
        assets[name] = {
            "href": f"https://{c1.C1_HOST}/{c1.C1_COLLECTION}/38/Q/ND/2026/10/{identity}/{band}.tif",
            "roles": ["data"] if name == "scl" else ["data", "reflectance"],
            "raster:bands": [
                {"scale": 1 if name == "scl" else 0.0001, "offset": 0 if name == "scl" else -0.1}
            ],
        }
    return {
        "item_id": identity,
        "datetime": captured,
        "bands_urls": {key: asset["href"] for key, asset in assets.items()},
        "radiometry_context": {
            "id": identity,
            "collection": c1.C1_COLLECTION,
            "properties": {"datetime": captured, "s2:processing_baseline": "05.11"},
            "assets": assets,
        },
    }


def _process(c1, scene, tmp_path, processed, **overrides):
    options = dict(
        scene=scene,
        index="ndvi",
        field="fld_test",
        tenant="tenant",
        geometry_revision=1,
        clip={
            "type": "Polygon",
            "coordinates": [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15]]],
        },
        apply_cloud_mask=True,
        jid="job",
        run_processing=lambda *args: processed.append(args),
        out_dir=str(tmp_path),
        entry_point="unit_boundary",
    )
    options.update(overrides)
    return c1.process_c1_scene(**options)


@pytest.mark.parametrize("defect", ["legacy", "identity", "missing_scl", "calibration", "origin"])
def test_unsafe_scene_never_reaches_vrt_or_processing(c1_boundary, c1_scene, tmp_path, defect):
    c1, rc, calls = c1_boundary
    scene = c1_scene
    if defect == "legacy":
        scene.pop("radiometry_context")
    elif defect == "identity":
        scene["radiometry_context"]["id"] = "another_item"
    elif defect == "missing_scl":
        del scene["bands_urls"]["scl"]
    elif defect == "calibration":
        del scene["radiometry_context"]["assets"]["red"]["raster:bands"][0]["scale"]
    else:
        scene["bands_urls"]["red"] = "https://untrusted.example/red.tif"
        scene["radiometry_context"]["assets"]["red"]["href"] = scene["bands_urls"]["red"]
    processed = []
    with pytest.raises(rc.RadiometryUnresolved):
        _process(c1, scene, tmp_path, processed)
    assert calls == [] and processed == []


@pytest.mark.parametrize(
    "override",
    [
        {"tenant": ""},
        {"field": ""},
        {"clip": None},
        {"apply_cloud_mask": False},
        {"index": "truecolor"},
    ],
)
def test_c1_still_requires_scope_clip_and_qa(c1_boundary, c1_scene, tmp_path, override):
    c1, rc, calls = c1_boundary
    processed = []
    with pytest.raises(rc.RadiometryUnresolved):
        _process(c1, c1_scene, tmp_path, processed, **override)
    assert calls == [] and processed == []


def test_admitted_c1_retains_bounded_calibration_and_qa_contract(c1_boundary, c1_scene, tmp_path):
    c1, _, calls = c1_boundary
    processed = []
    _process(c1, c1_scene, tmp_path, processed)
    assert len(calls) == len(processed) == 1
    kwargs = calls[0][2]
    assert kwargs["stac_item"] == c1_scene["radiometry_context"]
    assert kwargs["require_tiff_calibration"] is True
    assert kwargs["max_pixels"] == 1_000_000
    request = processed[0][1]
    assert request.raw_qa_required is True and request.apply_cloud_mask is True
    assert request.tenant_id == "tenant" and request.field_id == "fld_test"
    assert request.scene_id == c1_scene["item_id"]
    assert request.capture_datetime == c1_scene["datetime"]
    assert not Path(calls[0][1]).exists(), "VRT sidecars must be scoped to processing lifetime"

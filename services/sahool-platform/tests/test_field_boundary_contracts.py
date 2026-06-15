"""اختبارات عقود واجهة مراحل ML لحدود الحقل.

تغطّي: استبطان العقود بترتيب الـpipeline، تحقّق المدخلات/المخرجات (مفقود + نوع
خاطئ)، تحقّق AreaOfInterest/TimeWindow، أنّ RasterSource بروتوكول قابل للفحص،
وتكامل تحقّق العقد داخل run_pipeline لمراحل ML المُتجاوَزة فقط.
"""

from api.field_boundary_contracts import (
    SENTINEL2_BANDS,
    AreaOfInterest,
    CompositeRef,
    MLStageContract,
    RasterSource,
    TimeWindow,
    describe_contracts,
    validate_ml_stage_input,
    validate_ml_stage_output,
)
from api.field_boundary_pipeline import _STAGE_IMPLS, register_stage_impl, run_pipeline


def _restore_impls(saved):
    _STAGE_IMPLS.clear()
    _STAGE_IMPLS.update(saved)


# --- استبطان العقود -------------------------------------------------------


def test_describe_contracts_three_ml_stages_in_order():
    rows = describe_contracts()
    assert [r["stage_id"] for r in rows] == [
        "multi_temporal_composite",
        "crop_mask",
        "delineation",
    ]
    by_id = {r["stage_id"]: r for r in rows}
    assert by_id["multi_temporal_composite"]["required_input_keys"] == [
        "aoi",
        "time_window",
        "raster_source",
    ]
    assert by_id["multi_temporal_composite"]["required_output_keys"] == ["composite"]
    assert by_id["crop_mask"]["required_output_keys"] == ["crop_mask", "model_version"]
    assert by_id["delineation"]["output_types"]["polygons"] == "list"


def test_sentinel2_bands_are_standard_esa_ids():
    assert SENTINEL2_BANDS == ("B02", "B03", "B04", "B08", "B11", "B12")


# --- تحقّق المخرجات -------------------------------------------------------


def test_validate_output_passes_on_correct_dict():
    assert validate_ml_stage_output("delineation", {"polygons": [[0, 0], [1, 1]]}) == []


def test_validate_output_flags_missing_key():
    violations = validate_ml_stage_output("delineation", {})
    assert violations
    assert any("polygons" in v for v in violations)


def test_validate_output_flags_wrong_type():
    violations = validate_ml_stage_output("delineation", {"polygons": "notalist"})
    assert violations
    assert any("polygons" in v for v in violations)


def test_validate_output_unknown_stage():
    assert validate_ml_stage_output("nope", {}) == ["مرحلة ML غير معروفة: nope"]


# --- تحقّق المدخلات -------------------------------------------------------


def test_validate_input_flags_missing():
    violations = validate_ml_stage_input("multi_temporal_composite", {"aoi": 1})
    assert violations
    assert any("time_window" in v for v in violations)
    assert any("raster_source" in v for v in violations)


def test_validate_input_passes_when_present():
    ctx = {"aoi": 1, "time_window": 2, "raster_source": 3}
    assert validate_ml_stage_input("multi_temporal_composite", ctx) == []


def test_validate_input_unknown_stage():
    assert validate_ml_stage_input("nope", {}) == ["مرحلة ML غير معروفة: nope"]


# --- AreaOfInterest -------------------------------------------------------


def test_aoi_validate_happy():
    aoi = AreaOfInterest(bbox=(44.0, 15.0, 45.0, 16.0))
    assert aoi.validate() == []


def test_aoi_validate_violations():
    # minx >= maxx و خط عرض خارج المدى
    aoi = AreaOfInterest(bbox=(45.0, 15.0, 44.0, 200.0))
    violations = aoi.validate()
    assert violations
    assert any("minx" in v for v in violations)


# --- TimeWindow -----------------------------------------------------------


def test_time_window_validate_happy():
    assert TimeWindow(start="2024-01-01", end="2024-03-01").validate() == []


def test_time_window_validate_bad_order():
    violations = TimeWindow(start="2024-03-01", end="2024-01-01").validate()
    assert violations


def test_time_window_validate_unparseable():
    violations = TimeWindow(start="not-a-date", end="2024-01-01").validate()
    assert violations


# --- RasterSource protocol -----------------------------------------------


def test_raster_source_runtime_checkable():
    class DummySource:
        def fetch_composite(self, aoi, window, bands):
            return CompositeRef(
                band_names=tuple(bands),
                time_window=window,
                width=0,
                height=0,
                crs="EPSG:4326",
                source_uri=None,
            )

    assert isinstance(DummySource(), RasterSource)

    class NotASource:
        pass

    assert not isinstance(NotASource(), RasterSource)


def test_ml_stage_contract_dataclass_shape():
    c = MLStageContract(
        stage_id="x",
        required_input_keys=("a",),
        required_output_keys=("b",),
    )
    assert c.output_key_types == {}


# --- تكامل داخل run_pipeline ----------------------------------------------


def test_run_pipeline_contract_clean_for_real_delineation():
    saved = dict(_STAGE_IMPLS)
    try:

        @register_stage_impl("delineation")
        def _real_delineation(ctx):
            return {"polygons": [[0, 0], [1, 1]]}

        ctx = run_pipeline({})
        by_id = {row["stage"]: row for row in ctx["summary"]}
        row = by_id["delineation"]
        assert row["ran"] == "real"
        assert row["overridden"] is True
        assert row["contract_violations"] == []
    finally:
        _restore_impls(saved)


def test_run_pipeline_contract_flags_bad_real_output():
    saved = dict(_STAGE_IMPLS)
    try:

        @register_stage_impl("delineation")
        def _bad_delineation(ctx):
            return {"polygons": "notalist"}

        ctx = run_pipeline({})
        by_id = {row["stage"]: row for row in ctx["summary"]}
        row = by_id["delineation"]
        assert row["overridden"] is True
        assert row["contract_violations"]
    finally:
        _restore_impls(saved)


def test_run_pipeline_scaffold_has_no_contract_violations_key():
    ctx = run_pipeline({})
    by_id = {row["stage"]: row for row in ctx["summary"]}
    # مراحل ML السقالات لا تحمل مفتاح contract_violations
    assert "contract_violations" not in by_id["crop_mask"]
    # المراحل الحتميّة لا تحمله أيضاً
    assert "contract_violations" not in by_id["polygon_vectorize"]

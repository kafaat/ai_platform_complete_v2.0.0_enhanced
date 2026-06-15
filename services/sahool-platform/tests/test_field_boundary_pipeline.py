"""اختبارات إطار pipeline حدود الحقل (7 مراحل + حفظ).

تتحقّق من: ترتيب المراحل وأنواعها، صدق سقالات ML (لا تلفيق)، تجاوز التنفيذ
عبر register_stage_impl، ونقاء run_pipeline.
"""

from api.field_boundary_pipeline import (
    _STAGE_IMPLS,
    BOUNDARY_PIPELINE,
    PipelineStage,
    get_stage,
    list_stages,
    register_stage_impl,
    run_pipeline,
)

EXPECTED_ORDER = [
    ("multi_temporal_composite", "ml"),
    ("crop_mask", "ml"),
    ("delineation", "ml"),
    ("polygon_vectorize", "deterministic"),
    ("topology_clean", "deterministic"),
    ("confidence_score", "deterministic"),
    ("human_review", "hil"),
    ("persist", "persist"),
]


def _restore_impls(saved):
    _STAGE_IMPLS.clear()
    _STAGE_IMPLS.update(saved)


def test_list_stages_order_and_kinds():
    stages = list_stages()
    assert [(s["id"], s["kind"]) for s in stages] == EXPECTED_ORDER
    # 7 مراحل + حفظ = 8
    assert len(stages) == 8


def test_boundary_pipeline_frozen_dataclass():
    s = BOUNDARY_PIPELINE[0]
    assert isinstance(s, PipelineStage)
    import dataclasses

    try:
        s.id = "x"
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised


def test_get_stage():
    assert get_stage("crop_mask").kind == "ml"
    assert get_stage("persist").kind == "persist"
    import pytest

    with pytest.raises(KeyError):
        get_stage("nope")


def test_run_pipeline_marks_ml_as_unimplemented():
    ctx = run_pipeline({})
    assert ctx["unimplemented_stages"] == [
        "multi_temporal_composite",
        "crop_mask",
        "delineation",
    ]


def test_run_pipeline_does_not_fabricate_polygons():
    ctx = run_pipeline({})
    # لا مضلّعات/قناع مُلفّق
    assert ctx.get("polygons") is None
    assert ctx.get("confidence") is None
    assert ctx.get("review_status") == "unreviewed"
    assert ctx.get("persisted") is False


def test_ml_scaffold_returns_honest_marker():
    ctx = run_pipeline({})
    marker = ctx["crop_mask"]
    assert marker == {
        "status": "scaffold",
        "stage": "crop_mask",
        "note_ar": "تحتاج نموذج/راستر — غير مُنفّذة",
    }


def test_summary_distinguishes_real_vs_scaffold():
    ctx = run_pipeline({})
    by_id = {row["stage"]: row for row in ctx["summary"]}
    assert by_id["multi_temporal_composite"]["ran"] == "scaffold"
    assert by_id["polygon_vectorize"]["ran"] == "real"
    assert by_id["human_review"]["ran"] == "real"
    assert by_id["persist"]["ran"] == "real"


def test_run_pipeline_pure_does_not_mutate_input():
    original = {}
    run_pipeline(original)
    assert original == {}


def test_run_pipeline_none_ctx():
    ctx = run_pipeline()
    assert "summary" in ctx


def test_register_stage_impl_overrides():
    saved = dict(_STAGE_IMPLS)
    try:

        @register_stage_impl("delineation")
        def _fake_delineation(ctx):
            return {"polygons": [[0, 0], [1, 1]], "delineation_done": True}

        ctx = run_pipeline({})
        # المرحلة المُتجاوَزة لم تُسجَّل كغير مُنفّذة
        assert "delineation" not in ctx["unimplemented_stages"]
        assert ctx["delineation_done"] is True
        # المضلّعات الآن من التنفيذ الحقيقيّ (تمرّ عبر polygon_vectorize/topology)
        assert ctx["polygons"] == [[0, 0], [1, 1]]
        by_id = {row["stage"]: row for row in ctx["summary"]}
        assert by_id["delineation"]["ran"] == "real"
        assert by_id["delineation"]["overridden"] is True
    finally:
        _restore_impls(saved)


def test_register_stage_impl_unknown_stage_raises():
    import pytest

    with pytest.raises(KeyError):

        @register_stage_impl("not_a_stage")
        def _x(ctx):
            return {}

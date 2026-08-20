from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _polygon(x0: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [[x0, 15.0], [x0 + 0.001, 15.0], [x0 + 0.001, 15.001], [x0, 15.001], [x0, 15.0]]
        ],
    }


def test_adapt_edge_remains_deferred_until_real_b2b_trigger():
    decision = (ROOT / "services/sahool-platform/docs/REFERENCE_DOCS_CRITIQUE.md").read_text(
        encoding="utf-8"
    )
    assert "لا تبادل B2B لسهول" in decision
    assert not (ROOT / "shared/precision_agriculture/adapt_v2_edge.py").exists(), (
        "إسقاط ADAPT v2 مؤجَّلٌ عمداً حتّى يوجد مُحفِّز B2B حقيقيّ — كما يقرّر "
        "REFERENCE_DOCS_CRITIQUE.md. ووجودُ الوحدة ليس كسراً بل عودةُ سطحٍ تبادليّ "
        "قبل أوانه: شيفرةٌ قابلة للاستدعاء تُقرأ التزاماً بمعيارٍ لا نُطابقه ولا "
        "نختبره على شريكٍ حقيقيّ. أعِدها حين يوجد المُحفِّز، لا قبله."
    )
    exported = (ROOT / "shared/precision_agriculture/__init__.py").read_text(encoding="utf-8")
    assert "adapt_v2_edge" not in exported, (
        "التصدير أخطر من الملفّ: اسمٌ في `__init__` يجعل الإسقاط المؤجَّل واجهةً "
        "عامّةً يعتمد عليها مُستدعٍ، فيصير حذفُه لاحقاً كسراً لا تراجعاً."
    )


def test_spatial_rcbd_assignment_is_deterministic_and_balanced():
    m = _load("shared/precision_agriculture/trial_spatial.py", "delta_trial_spatial")
    treatments = ["شاهد", "N-low", "N-high"]
    geoms = [_polygon(44.0 + i * 0.002) for i in range(9)]
    a = m.assign_rcbd_geometries(
        trial_id="trial-1",
        treatments=treatments,
        n_blocks=3,
        plot_geometries=geoms,
        machine_heading_deg=372.0,
        randomization_seed="season-2026",
    )
    b = m.assign_rcbd_geometries(
        trial_id="trial-1",
        treatments=treatments,
        n_blocks=3,
        plot_geometries=geoms,
        machine_heading_deg=12.0,
        randomization_seed="season-2026",
    )
    assert [(r["plot_id"], r["treatment"]) for r in a] == [
        (r["plot_id"], r["treatment"]) for r in b
    ]
    assert all(r["machine_heading_deg"] == 12.0 for r in a)
    for block in (1, 2, 3):
        rows = [r for r in a if r["block_index"] == block]
        assert {r["treatment"] for r in rows} == set(treatments)
        assert sum(r["role"] == "control" for r in rows) == 1

    outcomes = {
        r["plot_id"]: {
            "outcome_refs": [f"yield:{r['plot_id']}"],
            "measurements": {"yield_t_ha": 3.2},
        }
        for r in a
    }
    bound = m.bind_plot_outcomes(a, outcomes)
    assert len(bound) == 9
    assert all(row["outcome_refs"] for row in bound)


def test_dataset_pedigree_requires_content_identity_and_builds_cross_domain_profile():
    m = _load("shared/mlops/runtime.py", "delta_mlops")
    ds = m.register_dataset_version(
        dataset_name="yemen-field-disease",
        version="2026.1",
        source_uri="s3://datasets/yemen-field-disease",
        source_revision="capture-2026-07",
        content_digest="a" * 64,
        license="internal-research-consent-v1",
        citation="SAHOOL field capture 2026",
        capture_country="YE",
        capture_region="Al Jawf",
        crop_scope=["wheat", "citrus", "wheat"],
        sensor_modality="rgb-mobile",
        annotation_format="coco",
        real_or_synthetic="real",
    )
    assert ds["crop_scope"] == ("wheat", "citrus")
    assert ds["content_digest"] == "a" * 64
    profile = m.agricultural_evaluation_profile(dataset_version_ids=[ds["dataset_version_id"]])
    assert profile["production_promotion_requires_all_slices"] is True
    assert {"lab", "field", "regional", "low_label", "ood"} <= set(profile["required_slices"])
    with pytest.raises(ValueError, match="content_digest"):
        m.register_dataset_version(
            dataset_name="bad",
            version="1",
            source_uri="x",
            source_revision="r",
            content_digest="",
            license="x",
        )


def test_thing_model_is_projection_not_new_execution_authority():
    m = _load("shared/iot_execution_runtime.py", "delta_iot")
    projection = m.project_thing_model(device_model_id="pivot-001")
    assert projection["authority"] == "projection_only"
    assert projection["physical_enable_required"] is True
    ids = {f["id"] for f in projection["functions"]}
    assert "dispatch:mqtt" in ids and "dispatch:modbus_tcp" in ids
    assert all(p["read_only"] for p in projection["properties"])


def test_raster_stage_receipt_is_deterministic_about_inputs_and_failures():
    m = _load("services/raster-service/raster_stage_receipt.py", "delta_raster_receipt")
    running = m.begin_stage(
        stage_id="raster.process",
        stage_version="v1",
        run_id="job-1",
        config={"index": "ndvi", "cloud": 20},
        input_refs=["scene:S2-A"],
    )
    assert running["status"] == "running" and len(running["config_digest"]) == 64
    done = m.finish_stage(running, output_refs=["asset:ndvi:abc"])
    assert done["status"] == "completed" and len(done["receipt_digest"]) == 64
    failed = m.fail_stage(running, RuntimeError("boom"))
    assert failed["status"] == "failed"
    assert failed["error_class"] == "RuntimeError"


def test_pail_observation_projection_is_semantic_only_and_provenance_bound():
    m = _load("shared/precision_agriculture/pail_om_edge.py", "delta_pail_om")
    projected = m.project_observation(
        observation_id="obs-1",
        property_code="soil_moisture",
        feature_of_interest="root_zone_soil",
        value=0.27,
        observed_at="2026-08-19T12:00:00Z",
        unit="m3/m3",
        field_id="field-1",
        device_id="probe-7",
        position={"lat": 15.75, "lon": 44.60},
        method_code="capacitance_probe",
        aggregation_code="instantaneous",
        quality_codes=["validated", "validated"],
        source_ref="telemetry:probe-7:obs-1",
    )
    assert projected.conformance_claim is False
    assert projected.observation["authority"] == "interchange_projection_only"
    assert projected.observation["code"]["property"] == "soil_moisture"
    assert projected.observation["quality_codes"] == ["validated"]
    assert projected.observation["source_ref"] == "telemetry:probe-7:obs-1"
    assert len(projected.content_digest) == 64

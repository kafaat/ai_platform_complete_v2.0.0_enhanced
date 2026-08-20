from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _squeeze(text: str) -> str:
    """يطوي المسافات البيضاء المتتابعة إلى فراغٍ واحد.

    يجعل تأكيدات النصّ المصدريّ محصَّنةً ضدّ إعادة لفّ `ruff format` — فما يُقاس
    هو العقد المكتوب في المصدر، لا الأسطر التي اختارها المُنسِّق له.
    """
    return re.sub(r"\s+", " ", text)


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _field_polygon() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [[44.0, 15.0], [44.004, 15.0], [44.004, 15.004], [44.0, 15.004], [44.0, 15.0]]
        ],
    }


def test_external_reference_provenance_is_mandatory_and_digest_bound():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import KnowledgeChunk

    with pytest.raises(ValueError, match="external reference provenance missing"):
        KnowledgeChunk(
            chunk_id="x",
            tenant_id="tenant-a",
            text="reference",
            source_type="official_reference",
            document_id="d",
            chunk_index=0,
            total_chunks=1,
            metadata={"evidence_level": "document", "source_class": "official_reference"},
        )

    with pytest.raises(ValueError, match="content_digest does not match"):
        KnowledgeChunk(
            chunk_id="x",
            tenant_id="tenant-a",
            text="reference",
            source_type="official_reference",
            document_id="d",
            chunk_index=0,
            total_chunks=1,
            metadata={
                "evidence_level": "document",
                "source_class": "official_reference",
                "publisher": "FAO",
                "source_uri": "https://example.invalid/fao",
                "source_revision": "2026",
                "license": "reference-use",
                "content_digest": "0" * 64,
            },
        )


def test_tenant_upload_provenance_is_mandatory_but_not_promoted_to_external_authority():
    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from core.rag.production_qdrant import KnowledgeChunk

    with pytest.raises(ValueError, match="tenant document provenance missing"):
        KnowledgeChunk(
            chunk_id="t",
            tenant_id="tenant-a",
            text="notes",
            source_type="uploaded_document",
            document_id="doc",
            chunk_index=0,
            total_chunks=1,
            metadata={"evidence_level": "document"},
        )
    chunk = KnowledgeChunk(
        chunk_id="t",
        tenant_id="tenant-a",
        text="notes",
        source_type="uploaded_document",
        document_id="doc",
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_uri": "tenant-upload://tenant-a/notes.txt",
            "source_revision": "sha256:file",
        },
    )
    assert chunk.metadata["source_class"] == "tenant_document"
    assert len(chunk.metadata["content_digest"]) == 64
    assert chunk.payload["metadata"]["prescriptive_eligible"] is False


def test_local_upload_and_seed_paths_cannot_bypass_provenance_contract():
    local = (ROOT / "services/local-ai-rag/main.py").read_text(encoding="utf-8")
    seed = (ROOT / "services/qdrant-seed/seed.py").read_text(encoding="utf-8")
    assert 'd.metadata["source_class"] = "tenant_document"' in local
    assert 'd.metadata["source_uri"] = f"tenant-upload://{tenant_id}/{original_name}"' in local
    assert 'd.metadata["source_revision"] = f"sha256:{file_digest}"' in local
    assert "source_names[str(tmp_path)] = Path(upload.filename).name" in local
    assert (
        'SEED_TENANT_ID = (os.getenv("QDRANT_SEED_TENANT_ID") or "__seed_quarantine__").strip()'
        in seed
    )
    assert "global reference seed requires QDRANT_SEED_PROVENANCE_FILE" in seed
    # تأكيدُ نصٍّ مصدريّ يُقارَن **بعد تطبيع المسافات**: `ruff format` — وهو بوّابة
    # حاجبة على كامل الشجرة — يعيد لفّ هذا الشرط الثلاثيّ على ثلاثة أسطر، فيصير
    # التأكيد الحرفيّ يقيس **تنسيق** الملفّ لا **عقده**. وقد وقع ذلك فعلاً: شجرةُ
    # V6 الخام تُدين `ruff format --check`، وتنسيقُها يُسقِط هذا التأكيد — أي أنّ
    # الشجرة لم تكن لتخضرّ في أيّ من الحالتين. المقيس هو وجود الحقل بشرطه.
    assert (
        '"provenance_status": "verified_manifest" if is_global else "legacy_unverified_quarantine"'
        in _squeeze(seed)
    )


def test_spatial_rcbd_generates_complete_machine_aligned_plots_inside_field():
    m = _load("shared/precision_agriculture/trial_spatial.py", "v6_trial_spatial")
    rows = m.design_spatial_rcbd(
        trial_id="trial-v6",
        treatments=["control", "N-low", "N-high"],
        n_blocks=3,
        field_geometry=_field_polygon(),
        machine_heading_deg=17.0,
        implement_width_m=20.0,
        randomization_seed="season-2026",
        headland_m=5.0,
        strip_gap_m=1.0,
        min_plot_area_m2=500.0,
    )
    assert len(rows) == 9
    assert all(row["area_m2"] and row["area_m2"] >= 500 for row in rows)
    assert {row["block_index"] for row in rows} == {1, 2, 3}
    for block in (1, 2, 3):
        block_rows = [r for r in rows if r["block_index"] == block]
        assert {r["treatment"] for r in block_rows} == {"control", "N-low", "N-high"}
        assert sum(r["role"] == "control" for r in block_rows) == 1
    with pytest.raises(ValueError, match="implement-width strips"):
        m.design_spatial_rcbd(
            trial_id="narrow",
            treatments=["control", "a", "b"],
            n_blocks=3,
            field_geometry=_field_polygon(),
            machine_heading_deg=0,
            implement_width_m=500,
            randomization_seed="x",
        )


def test_trial_raster_zonal_outcomes_bind_real_pixels(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_bounds

    spatial = _load("shared/precision_agriculture/trial_spatial.py", "v6_trial_spatial_zonal")
    zonal = _load("services/raster-service/trial_zonal_outcomes.py", "v6_trial_zonal")
    assignments = spatial.design_spatial_rcbd(
        trial_id="trial-zonal",
        treatments=["control", "treatment"],
        n_blocks=2,
        field_geometry=_field_polygon(),
        machine_heading_deg=0.0,
        implement_width_m=20,
        randomization_seed="seed",
        headland_m=2,
        min_plot_area_m2=500,
    )
    path = tmp_path / "yield.tif"
    data = np.arange(10000, dtype="float32").reshape(100, 100)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=100,
        height=100,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_bounds(44.0, 15.0, 44.004, 15.004, 100, 100),
    ) as dst:
        dst.write(data, 1)
    outcomes = zonal.extract_plot_zonal_outcomes(
        assignments,
        [{"name": "yield", "path": str(path), "evidence_ref": "raster:yield:v1"}],
    )
    bound = spatial.bind_plot_outcomes(assignments, outcomes)
    assert len(bound) == len(assignments)
    assert all(row["outcome_refs"] == ("raster:yield:v1",) for row in bound)
    assert all(row["measurements"]["yield_count"] > 0 for row in bound)
    assert all(np.isfinite(row["measurements"]["yield_mean"]) for row in bound)


def test_adapt_field_boundary_roundtrip_is_identity_preserving_and_bounded():
    m = _load("shared/precision_agriculture/adapt_v2_edge.py", "v6_adapt")
    source = _field_polygon()
    bundle = m.export_field_boundary_bundle(
        field_id="f-17", field_name="Pivot 17", geometry=source, boundary_revision="42"
    )
    restored = m.import_field_boundary_bundle(bundle.document)
    assert restored["field_id"] == "f-17"
    assert restored["field_name"] == "Pivot 17"
    assert restored["boundary_revision"] == "42"
    assert restored["geometry"] == source
    assert restored["authority"] == "interchange_roundtrip_only"
    tampered = json.loads(json.dumps(bundle.document))
    tampered["catalog"]["fieldBoundaries"][0]["fieldId"] = "sahool:field:other"
    with pytest.raises(ValueError, match="inconsistent"):
        m.import_field_boundary_bundle(tampered)


def test_pail_projection_roundtrip_rejects_digest_or_authority_tamper():
    m = _load("shared/precision_agriculture/pail_om_edge.py", "v6_pail")
    projected = m.project_observation(
        observation_id="obs-v6",
        property_code="soil_moisture",
        feature_of_interest="root_zone",
        value=0.31,
        observed_at="2026-08-20T00:00:00Z",
        unit="m3/m3",
        field_id="field-1",
        device_id="probe-1",
        source_ref="telemetry:probe-1:obs-v6",
    )
    restored = m.import_observation_projection(projected)
    assert restored["observation_id"] == "obs-v6"
    assert restored["property_code"] == "soil_moisture"
    assert restored["authority"] == "interchange_roundtrip_only"
    tampered = {
        "mapping_version": projected.mapping_version,
        "reference_model": projected.reference_model,
        "observation": {**projected.observation, "value": 0.99},
        "content_digest": projected.content_digest,
        "conformance_claim": False,
    }
    with pytest.raises(ValueError, match="content_digest mismatch"):
        m.import_observation_projection(tampered)


def test_raster_stage_dag_enforces_cycle_dependency_and_lineage():
    m = _load("services/raster-service/raster_stage_receipt.py", "v6_raster_dag")
    graph = m.build_stage_graph(
        [
            {"stage_id": "decode", "stage_version": "v1"},
            {"stage_id": "index", "stage_version": "v2", "dependency_stage_ids": ["decode"]},
            {"stage_id": "publish", "stage_version": "v1", "dependency_stage_ids": ["index"]},
        ]
    )
    assert graph["topological_order"] == ["decode", "index", "publish"]
    decode = m.begin_stage(
        stage_id="decode",
        stage_version="v1",
        run_id="job-v6",
        config={"src": "S2"},
        stage_graph=graph,
        input_refs=["scene:S2"],
    )
    decode_done = m.finish_stage(decode, output_refs=["asset:decoded"])
    assert m.verify_receipt(decode_done)
    index = m.begin_stage(
        stage_id="index",
        stage_version="v2",
        run_id="job-v6",
        config={"index": "ndvi"},
        dependency_stage_ids=["decode"],
        dependency_receipts={"decode": decode_done},
        stage_graph=graph,
        input_refs=["asset:decoded"],
    )
    index_done = m.finish_stage(index, output_refs=["asset:ndvi"])
    publish = m.begin_stage(
        stage_id="publish",
        stage_version="v1",
        run_id="job-v6",
        config={},
        dependency_stage_ids=["index"],
        dependency_receipts={"index": index_done},
        stage_graph=graph,
        input_refs=["asset:ndvi"],
    )
    assert publish["dependency_receipt_digests"] == [index_done["receipt_digest"]]
    with pytest.raises(ValueError, match="cycle"):
        m.build_stage_graph(
            [
                {"stage_id": "a", "stage_version": "v1", "dependency_stage_ids": ["b"]},
                {"stage_id": "b", "stage_version": "v1", "dependency_stage_ids": ["a"]},
            ]
        )
    with pytest.raises(ValueError, match="do not carry"):
        m.begin_stage(
            stage_id="index",
            stage_version="v2",
            run_id="job-v6",
            config={},
            dependency_stage_ids=["decode"],
            dependency_receipts={"decode": decode_done},
            stage_graph=graph,
            input_refs=["wrong:input"],
        )
    bad = dict(index_done)
    bad["output_refs"] = ["tampered"]
    with pytest.raises(ValueError, match="digest mismatch"):
        m.verify_receipt(bad)


def test_spatial_trial_and_zonal_extraction_have_non_test_consumers():
    router = (ROOT / "services/sahool-platform/api/routers/trials.py").read_text(encoding="utf-8")
    models = (ROOT / "services/sahool-platform/api/trial_models.py").read_text(encoding="utf-8")
    runtime = (ROOT / "services/raster-service/raster_processing_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "spatial_plan: SpatialTrialPlanInput | None" in models
    assert "design_spatial_rcbd(" in router
    assert 'out["spatial_trial"]' in router
    assert "trial_zonal_outcomes.extract_plot_zonal_outcomes" in runtime


def test_canonical_ingest_classifies_invalid_provenance_as_422():
    source = (ROOT / "services/rag-retrieval/main.py").read_text(encoding="utf-8")
    assert '"code": "INVALID_RAG_PROVENANCE"' in source
    assert "status_code=422" in source


def test_global_seed_requires_explicit_provenance_manifest():
    source = (ROOT / "services/qdrant-seed/seed.py").read_text(encoding="utf-8")
    assert (
        'SEED_PROVENANCE_FILE = (os.getenv("QDRANT_SEED_PROVENANCE_FILE") or "").strip()' in source
    )
    assert (
        'SEED_PROVENANCE_JSON = (os.getenv("QDRANT_SEED_PROVENANCE_JSON") or "").strip()' in source
    )
    assert (
        "global reference seed requires QDRANT_SEED_PROVENANCE_FILE or QDRANT_SEED_PROVENANCE_JSON"
        in source
    )
    assert "missing_sources = sorted(" in source
    # تأكيدُ نصٍّ مصدريّ يُقارَن **بعد تطبيع المسافات**: `ruff format` — وهو بوّابة
    # حاجبة على كامل الشجرة — يعيد لفّ هذا الشرط الثلاثيّ على ثلاثة أسطر، فيصير
    # التأكيد الحرفيّ يقيس **تنسيق** الملفّ لا **عقده**. وقد وقع ذلك فعلاً: شجرةُ
    # V6 الخام تُدين `ruff format --check`، وتنسيقُها يُسقِط هذا التأكيد — أي أنّ
    # الشجرة لم تكن لتخضرّ في أيّ من الحالتين. المقيس هو وجود الحقل بشرطه.
    assert (
        '"provenance_status": "verified_manifest" if is_global else "legacy_unverified_quarantine"'
        in _squeeze(source)
    )

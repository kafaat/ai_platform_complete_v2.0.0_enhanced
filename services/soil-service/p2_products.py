"""Deterministic P2 spatial product kernels; no synthetic measured evidence."""

from __future__ import annotations

import math
import statistics

from shared.contracts.soil import (
    BareSoilComposite,
    BareSoilCompositeRequest,
    SalinityAssessmentProduct,
    SalinityAssessmentRequest,
    SalinityZoneAssessment,
    TerrainDerivativesProduct,
    TerrainRequest,
    TextureFeatureVector,
    TextureProbabilityProduct,
    TextureProbabilityRequest,
    TextureZoneProbability,
)


def _median(xs):
    return statistics.median(xs) if xs else 0.0


def _clamp(x):
    return max(0.0, min(1.0, float(x)))


def build_bare_soil_composite(r: BareSoilCompositeRequest) -> BareSoilComposite:
    thresholds = (
        r.min_bare_fraction,
        r.max_cloud_fraction,
        r.max_shadow_fraction,
        r.max_vegetation_fraction,
    )
    if not all(0 <= threshold <= 1 for threshold in thresholds):
        raise ValueError("scene_quality_thresholds_must_be_fractions")
    chosen = []
    rejected = {}
    seen = {}
    for s in r.scenes:
        if not s.scene_id.strip():
            raise ValueError("scene_id_required")
        if s.scene_id in seen:
            if seen[s.scene_id] != s:
                raise ValueError("conflicting_duplicate_scene_id")
            continue
        seen[s.scene_id] = s
        why = []
        if s.cloud_fraction > r.max_cloud_fraction:
            why.append("cloud")
        if s.shadow_fraction > r.max_shadow_fraction:
            why.append("shadow")
        if s.vegetation_fraction > r.max_vegetation_fraction:
            why.append("vegetation")
        if s.bare_fraction < r.min_bare_fraction or s.bare_fraction == 0:
            why.append("insufficient_bare_soil")
        if not s.band_means or not all(
            band.strip() and math.isfinite(value) for band, value in s.band_means.items()
        ):
            why.append("missing_or_nonfinite_bands")
        if why:
            rejected[s.scene_id] = why
        else:
            chosen.append(s)
    if not chosen:
        raise ValueError("no_eligible_bare_soil_scenes")
    bands = sorted({b for s in chosen for b in s.band_means})
    med = {}
    band_scenes = {}
    for band in bands:
        supporting = [s for s in chosen if band in s.band_means]
        med[band] = round(_median([s.band_means[band] for s in supporting]), 8)
        band_scenes[band] = [s.scene_id for s in supporting]
    quality = [
        s.bare_fraction
        * (1 - s.cloud_fraction)
        * (1 - s.shadow_fraction)
        * (1 - s.vegetation_fraction)
        for s in chosen
    ]
    confidence = _clamp(_median(quality) * (1 - math.exp(-len(chosen) / 3)))
    return BareSoilComposite(
        tenant_id=r.tenant_id,
        field_id=r.field_id,
        geometry_hash=r.geometry_hash,
        algorithm_version=r.algorithm_version,
        selected_scene_ids=[s.scene_id for s in chosen],
        rejected_scenes=rejected,
        normalized_band_medians=med,
        confidence_score=round(confidence, 6),
        confidence_mask_summary={
            "eligible_scene_count": float(len(chosen)),
            "rejected_scene_count": float(len(rejected)),
            "median_bare_fraction": round(_median([s.bare_fraction for s in chosen]), 6),
        },
        provenance={
            "scene_acquisitions": {s.scene_id: s.acquired_at.isoformat() for s in chosen},
            "source_uris": {s.scene_id: s.source_uri for s in chosen if s.source_uri},
            "band_scene_ids": band_scenes,
            "aggregation": "median_of_scene_band_means",
            "moisture_normalization": "not_applied",
            "moisture_proxy_by_scene": {s.scene_id: s.moisture_proxy for s in chosen},
            "confidence_basis": "heuristic_scene_quality_and_count",
        },
    )


def _stats(vals):
    return {
        "min": round(min(vals), 6),
        "max": round(max(vals), 6),
        "mean": round(statistics.fmean(vals), 6),
        "median": round(_median(vals), 6),
    }


def build_terrain_derivatives(r: TerrainRequest) -> TerrainDerivativesProduct:
    z = r.elevation_m
    h = len(z)
    w = len(z[0])
    cs = r.cell_size_m
    metrics = {
        k: []
        for k in (
            "slope_deg",
            "tpi",
            "local_wetness_proxy",
            "elevation_laplacian_per_m",
            "row_second_derivative_per_m",
            "higher_neighbor_count",
            "relative_elevation",
        )
    }
    land = {}
    depressions = []
    zmin = min(map(min, z))
    zmax = max(map(max, z))
    for i in range(1, h - 1):
        for j in range(1, w - 1):
            dzdx = (z[i][j + 1] - z[i][j - 1]) / (2 * cs)
            dzdy = (z[i + 1][j] - z[i - 1][j]) / (2 * cs)
            slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
            neigh = [
                z[ii][jj]
                for ii in range(i - 1, i + 2)
                for jj in range(j - 1, j + 2)
                if (ii, jj) != (i, j)
            ]
            tpi = z[i][j] - statistics.fmean(neigh)
            lap = (z[i][j - 1] + z[i][j + 1] + z[i - 1][j] + z[i + 1][j] - 4 * z[i][j]) / (cs * cs)
            prof = (z[i + 1][j] - 2 * z[i][j] + z[i - 1][j]) / (cs * cs)
            higher_neighbors = sum(x > z[i][j] for x in neigh)
            twi = math.log(
                ((1 + higher_neighbors) * cs) / max(math.tan(math.radians(max(slope, 0.01))), 0.001)
            )
            rel = (z[i][j] - zmin) / max(zmax - zmin, 1e-9)
            vals = (slope, tpi, twi, lap, prof, float(higher_neighbors), rel)
            for k, v in zip(metrics, vals, strict=True):
                metrics[k].append(v)
            klass = (
                "ridge"
                if tpi > 1
                else "depression"
                if tpi < -1
                else "slope"
                if slope > 5
                else "plain"
            )
            land[klass] = land.get(klass, 0) + 1
            if z[i][j] < min(neigh):
                depressions.append(
                    {
                        "row": i,
                        "col": j,
                        "elevation_m": z[i][j],
                        "depth_proxy_m": round(min(neigh) - z[i][j], 4),
                    }
                )
    return TerrainDerivativesProduct(
        tenant_id=r.tenant_id,
        field_id=r.field_id,
        geometry_hash=r.geometry_hash,
        dem_version=r.dem_version,
        algorithm_version="terrain-v2",
        shape=[h, w],
        summaries={k: _stats(v) for k, v in metrics.items()},
        drainage_paths=[],
        depressions=depressions,
        landform_counts=land,
        provenance={
            "cell_size_m": cs,
            "algorithm": "finite_difference_3x3_v2",
            "unavailable": {
                "wadi_distance_m": "no_wadi_geometry",
                "flow_accumulation": "no_flow_routing",
                "drainage_paths": "no_flow_routing",
                "twi": "no_upslope_contributing_area",
            },
            "limitations": [
                "engineering drainage design requires surveyed elevations and field verification"
            ],
        },
    )


def _texture_est(f: TextureFeatureVector):
    # SoilGrids reports fine-earth particle mass fractions. Only a missing third
    # component may be derived by closure. Terrain and spectral indices alone
    # have no locally validated conversion to percent clay, sand or silt.
    fractions = [f.soilgrids.get(name) for name in ("clay_pct", "sand_pct", "silt_pct")]
    available = [v for v in fractions if v is not None]
    if len(available) < 2:
        return None
    if not all(math.isfinite(v) and 0 <= v <= 100 for v in available):
        return None
    total = sum(available)
    if len(available) == 2:
        if total > 100:
            return None
        return tuple(100 - total if v is None else v for v in fractions)
    if abs(total - 100) > 1:
        return None
    return tuple(v * 100 / total for v in available)


def build_texture_probability(r: TextureProbabilityRequest) -> TextureProbabilityProduct:
    from shared.soil_texture import usda_texture_class

    zones = []
    skipped = []
    for f in r.features:
        estimate = _texture_est(f)
        if estimate is None:
            skipped.append(f.zone_id)
            continue
        clay, sand, silt = estimate
        texture = usda_texture_class(clay, sand, silt)["key"].replace(" ", "_")
        zones.append(
            TextureZoneProbability(
                zone_id=f.zone_id,
                clay_probability=round(clay / 100, 6),
                sand_probability=round(sand / 100, 6),
                silt_probability=round(silt / 100, 6),
                texture_class=texture,
                uncertainty=None,
                estimated_clay_pct=round(clay, 3),
                estimated_sand_pct=round(sand, 3),
                estimated_silt_pct=round(silt, 3),
            )
        )
    # deterministic spatial-CV readiness statement; no false accuracy claim without samples
    cv = {
        "method": "spatial_block",
        "folds": r.validation_folds,
        "sample_count": len(r.calibration_samples),
        "status": "not_evaluated"
        if len(r.calibration_samples) >= r.validation_folds * 3
        else "insufficient_local_samples",
        "metrics": {},
    }
    return TextureProbabilityProduct(
        tenant_id=r.tenant_id,
        field_id=r.field_id,
        geometry_hash=r.geometry_hash,
        model_version=r.model_version,
        zones=zones,
        spatial_cv=cv,
        provenance={
            "inputs": ["soilgrids"] if zones else [],
            "method": "soilgrids_particle_fractions_usda_triangle",
            "uncertainty_status": "not_estimated",
            "texture_status": "estimated" if zones else "insufficient_evidence",
            "zones_without_usable_inputs": skipped,
            "probability_fields": "estimated_composition_fractions",
            "evidence_class": "modelled",
            "local_calibration_samples": len(r.calibration_samples),
        },
    )


def build_salinity_assessment(r: SalinityAssessmentRequest) -> SalinityAssessmentProduct:
    out = []
    for z in r.zones:
        has_ece = z.ec_lab_ds_m is not None and z.ec_lab_method == "saturation_extract_25c"
        notes = []
        if z.ec_lab_ds_m is not None and not has_ece:
            notes.append("soil_ec_not_comparable_to_saturation_extract_25c")
        # USDA-NRCS SSIR 42, method 4F2. These flags concern the supplied
        # sample, and do not establish a verified or calibrated zone.
        elevated_ece = has_ece and z.ec_lab_ds_m >= 4
        elevated_esp = z.esp_pct is not None and z.esp_pct >= 15
        if has_ece:
            notes.append("reported_ece_at_or_above_4" if elevated_ece else "reported_ece_below_4")
        if z.esp_pct is not None:
            notes.append("reported_esp_at_or_above_15" if elevated_esp else "reported_esp_below_15")
        sal = _clamp(
            0.35 * z.salinity_index
            + 0.2 * z.persistence
            + 0.2 * z.drainage_risk
            + 0.15 * (min(z.ec_lab_ds_m / 8, 1) if has_ece else 0)
            + 0.1 * (min((z.ecw_ds_m or 0) / 4, 1))
        )
        sod = _clamp(
            0.45 * min((z.esp_pct or 0) / 15, 1)
            + 0.35 * min((z.sar or 0) / 18, 1)
            + 0.2 * z.drainage_risk
        )
        gypsum = _clamp(
            0.55 * z.gypsum_index
            + 0.2 * z.brightness
            + 0.15 * (1 - z.salinity_index)
            + 0.1 * (1 - z.persistence)
        )
        carb = _clamp(0.65 * z.carbonate_index + 0.2 * z.brightness + 0.15 * (1 - z.salinity_index))
        sand = _clamp(
            0.55 * z.brightness
            + 0.25 * (1 - z.persistence)
            + 0.2 * (1 - z.drainage_risk)
            - 0.25 * max(gypsum, carb)
        )
        salinity_signal = elevated_ece or sal >= 0.6
        sodicity_signal = elevated_esp or sod >= 0.6
        cls = (
            "saline_sodic_candidate"
            if salinity_signal and sodicity_signal
            else "saline_candidate"
            if salinity_signal
            else "sodic_candidate"
            if sodicity_signal
            else "gypsic_candidate"
            if gypsum >= 0.65
            else "calcareous_candidate"
            if carb >= 0.65
            else "bright_sand_candidate"
            if sand >= 0.65
            else "low_signal"
        )
        out.append(
            SalinityZoneAssessment(
                zone_id=z.zone_id,
                salinity_probability=round(sal, 6),
                sodicity_probability=round(sod, 6),
                gypsum_probability=round(gypsum, 6),
                carbonate_probability=round(carb, 6),
                bright_sand_probability=round(sand, 6),
                uncertainty=0.55,
                classification=cls,
                evidence_notes=notes,
                evidence_level="screening",
                allowed_use=["screening", "sampling_priority"],
                blocked_use=["gypsum_rate", "leaching_requirement", "reclamation_execution"],
            )
        )
    return SalinityAssessmentProduct(
        tenant_id=r.tenant_id,
        field_id=r.field_id,
        geometry_hash=r.geometry_hash,
        model_version=r.model_version,
        zones=out,
        provenance={
            "model": "salinity_screening_v2",
            "probability_fields": "uncalibrated_screening_scores",
            "uncertainty_field": "legacy_heuristic_not_validated",
            "threshold_reference": "USDA NRCS SSIR 42 v6, method 4F2",
            "lab_input_provenance": "caller_reported_unverified",
            # Enforced by p4_governance (minimum_evidence_level="lab_verified").
            "high_risk_actions_require_lab_verified": "true",
        },
    )

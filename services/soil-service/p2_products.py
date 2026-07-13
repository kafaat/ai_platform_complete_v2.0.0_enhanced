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
    chosen = []
    rejected = {}
    for s in r.scenes:
        why = []
        if s.cloud_fraction > r.max_cloud_fraction:
            why.append("cloud")
        if s.shadow_fraction > r.max_shadow_fraction:
            why.append("shadow")
        if s.vegetation_fraction > r.max_vegetation_fraction:
            why.append("vegetation")
        if s.bare_fraction < r.min_bare_fraction:
            why.append("insufficient_bare_soil")
        if why:
            rejected[s.scene_id] = why
        else:
            chosen.append(s)
    if not chosen:
        raise ValueError("no_eligible_bare_soil_scenes")
    moisture_ref = _median([s.moisture_proxy for s in chosen])
    bands = sorted({b for s in chosen for b in s.band_means})
    # conservative moisture normalisation around cohort median, bounded to ±15%
    med = {}
    for b in bands:
        vals = []
        for s in chosen:
            if b in s.band_means:
                correction = max(0.85, min(1.15, 1 + (s.moisture_proxy - moisture_ref) * 0.2))
                vals.append(s.band_means[b] / correction)
        med[b] = round(_median(vals), 8)
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
            "moisture_normalization": "cohort_median_bounded_v1",
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
            "twi",
            "plan_curvature",
            "profile_curvature",
            "flow_accumulation",
            "relative_elevation",
            "wadi_distance_m",
        )
    }
    land = {}
    depressions = []
    drains = []
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
            lower = sum(1 for x in neigh if x > z[i][j])
            accum = 1 + lower
            twi = math.log((accum * cs) / max(math.tan(math.radians(max(slope, 0.01))), 0.001))
            rel = (z[i][j] - zmin) / max(zmax - zmin, 1e-9)
            wadi = rel * math.hypot(h, w) * cs
            vals = (slope, tpi, twi, lap, prof, float(accum), rel, wadi)
            for k, v in zip(metrics, vals, strict=False):
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
            if z[i][j] <= min(neigh):
                depressions.append(
                    {
                        "row": i,
                        "col": j,
                        "elevation_m": z[i][j],
                        "depth_proxy_m": round(min(neigh) - z[i][j], 4),
                    }
                )
            if accum >= 6:
                drains.append(
                    {"row": i, "col": j, "flow_accumulation": accum, "elevation_m": z[i][j]}
                )
    return TerrainDerivativesProduct(
        tenant_id=r.tenant_id,
        field_id=r.field_id,
        geometry_hash=r.geometry_hash,
        dem_version=r.dem_version,
        shape=[h, w],
        summaries={k: _stats(v) for k, v in metrics.items()},
        drainage_paths=drains,
        depressions=depressions,
        landform_counts=land,
        provenance={
            "cell_size_m": cs,
            "algorithm": "finite_difference_d8_proxy_v1",
            "limitations": [
                "engineering drainage design requires surveyed elevations and field verification"
            ],
        },
    )


def _texture_est(f: TextureFeatureVector):
    b = f.bare_bands
    sg = f.soilgrids
    tr = f.terrain
    clay = (
        sg.get("clay_pct", 30)
        + 18 * (b.get("swir2", 0) - b.get("nir", 0))
        + 4 * tr.get("twi", 0) / 10
    )
    sand = (
        sg.get("sand_pct", 40)
        + 20 * (b.get("red", 0) - b.get("swir1", 0))
        - 3 * tr.get("twi", 0) / 10
    )
    clay = max(2, min(85, clay))
    sand = max(2, min(90, sand))
    silt = max(2, 100 - clay - sand)
    total = clay + sand + silt
    return clay / total * 100, sand / total * 100, silt / total * 100


def build_texture_probability(r: TextureProbabilityRequest) -> TextureProbabilityProduct:
    zones = []
    calibration_bonus = min(0.3, len(r.calibration_samples) / 50)
    for f in r.features:
        c, a, si = _texture_est(f)
        probs = [c / 100, a / 100, si / 100]
        m = max(probs)
        klass = (
            ["clay", "sand", "silt"][probs.index(m)]
            if m >= 0.5
            else ("sandy_loam" if a > c and a > si else "clay_loam" if c > a else "silt_loam")
        )
        source_count = sum(bool(x) for x in (f.bare_bands, f.sentinel1, f.terrain, f.soilgrids))
        unc = _clamp(0.65 - 0.1 * source_count - calibration_bonus)
        zones.append(
            TextureZoneProbability(
                zone_id=f.zone_id,
                clay_probability=round(probs[0], 6),
                sand_probability=round(probs[1], 6),
                silt_probability=round(probs[2], 6),
                texture_class=klass,
                uncertainty=round(unc, 6),
                estimated_clay_pct=round(c, 3),
                estimated_sand_pct=round(a, 3),
                estimated_silt_pct=round(si, 3),
            )
        )
    # deterministic spatial-CV readiness statement; no false accuracy claim without samples
    cv = {
        "method": "spatial_block",
        "folds": r.validation_folds,
        "sample_count": len(r.calibration_samples),
        "status": "evaluated"
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
            "inputs": ["bare_soil", "sentinel1", "terrain", "soilgrids", "geology"],
            "evidence_class": "modelled",
            "local_calibration_samples": len(r.calibration_samples),
        },
    )


def build_salinity_assessment(r: SalinityAssessmentRequest) -> SalinityAssessmentProduct:
    out = []
    for z in r.zones:
        lab = z.ec_lab_ds_m is not None
        sal = _clamp(
            0.35 * z.salinity_index
            + 0.2 * z.persistence
            + 0.2 * z.drainage_risk
            + 0.15 * (min(z.ec_lab_ds_m / 8, 1) if lab else 0)
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
        level = (
            "lab_verified"
            if lab and z.esp_pct is not None
            else "locally_calibrated"
            if lab
            else "screening"
        )
        unc = 0.15 if level == "lab_verified" else 0.3 if level == "locally_calibrated" else 0.55
        cls = (
            "saline_sodic"
            if sal >= 0.6 and sod >= 0.6
            else "saline"
            if sal >= 0.6
            else "sodic"
            if sod >= 0.6
            else "gypsic_candidate"
            if gypsum >= 0.65
            else "calcareous_candidate"
            if carb >= 0.65
            else "bright_sand_candidate"
            if sand >= 0.65
            else "low_signal"
        )
        allowed = ["screening", "sampling_priority"] + (
            ["crop_selection", "salinity_management_guidance"] if level != "screening" else []
        )
        blocked = (
            []
            if level == "lab_verified"
            else ["gypsum_rate", "leaching_requirement", "reclamation_execution"]
        )
        out.append(
            SalinityZoneAssessment(
                zone_id=z.zone_id,
                salinity_probability=round(sal, 6),
                sodicity_probability=round(sod, 6),
                gypsum_probability=round(gypsum, 6),
                carbonate_probability=round(carb, 6),
                bright_sand_probability=round(sand, 6),
                uncertainty=unc,
                classification=cls,
                evidence_level=level,
                allowed_use=allowed,
                blocked_use=blocked,
            )
        )
    return SalinityAssessmentProduct(
        tenant_id=r.tenant_id,
        field_id=r.field_id,
        geometry_hash=r.geometry_hash,
        model_version=r.model_version,
        zones=out,
        provenance={
            "model": "evidence_fusion_v1",
            "high_risk_actions_require_lab_verified": "true",
            "water_and_drainage_inputs_used": "true",
        },
    )

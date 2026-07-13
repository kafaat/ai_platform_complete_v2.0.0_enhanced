"""Pure governed builders for P1 soil products."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import uuid4

from shared.contracts.soil import (
    EvidenceOrigin,
    HydraulicValue,
    IrrigationWaterProfile,
    IrrigationWaterSample,
    SamplingPlan,
    SamplingPlanRequest,
    SamplingPoint,
    SoilHydraulicLayer,
    SoilHydraulicProfile,
)


def build_sampling_plan(req: SamplingPlanRequest) -> SamplingPlan:
    targets = {
        "economic": max(3, len({c.zone_id for c in req.candidates})),
        "balanced": max(5, 2 * len({c.zone_id for c in req.candidates})),
        "high_accuracy": max(8, 3 * len({c.zone_id for c in req.candidates})),
    }
    target = min(req.target_count or targets[req.mode], 200)
    eligible = []
    excluded = {"inaccessible": 0, "boundary_buffer": 0}
    for c in req.candidates:
        if not c.accessible:
            excluded["inaccessible"] += 1
            continue
        if c.boundary_distance_m < req.min_boundary_buffer_m:
            excluded["boundary_buffer"] += 1
            continue
        score = (
            0.45 * c.uncertainty + 0.25 * c.anomaly + 0.20 * c.transition + 0.10 * (1 - c.stability)
        )
        reasons = []
        if c.uncertainty >= 0.6:
            reasons.append("high_uncertainty")
        if c.anomaly >= 0.6:
            reasons.append("anomaly")
        if c.transition >= 0.6:
            reasons.append("transition")
        eligible.append((score, c, reasons or ["zone_representation"]))
    # round-robin by zone first, then global score to avoid zone starvation
    by = {}
    for item in sorted(eligible, key=lambda x: x[0], reverse=True):
        by.setdefault(item[1].zone_id, []).append(item)
    selected = []
    while len(selected) < target and any(by.values()):
        for zone in sorted(by):
            if by[zone] and len(selected) < target:
                selected.append(by[zone].pop(0))
    points = [
        SamplingPoint(
            candidate_id=c.id,
            lon=c.lon,
            lat=c.lat,
            zone_id=c.zone_id,
            rank=i + 1,
            score=round(s, 6),
            reasons=r,
            depths_cm=req.depths_cm,
        )
        for i, (s, c, r) in enumerate(selected)
    ]
    return SamplingPlan(
        plan_id=f"ssp_{uuid4().hex}",
        tenant_id=req.tenant_id,
        field_id=req.field_id,
        mode=req.mode,
        created_at=datetime.now(UTC),
        points=points,
        excluded=excluded,
        approval_required=req.require_approval,
    )


def _hv(v, unit, origin, confidence, ids):
    return HydraulicValue(
        value=round(v, 6),
        unit=unit,
        origin=origin,
        confidence=confidence,
        source_observation_ids=ids,
    )


def build_hydraulic_profile(snapshot) -> SoilHydraulicProfile:
    layers = []
    available = 0
    total = 0
    for layer in snapshot.layers:
        p = layer.properties
        ids = [x.source_id for x in p.values() if x.source_id]

        def num(k, props=p):
            x = props.get(k)
            return float(x.value) if x and isinstance(x.value, (int, float)) else None

        sand = num("sand_pct")
        clay = num("clay_pct")
        om = num("organic_matter")
        cf = num("coarse_fragments") or 0
        fc = num("field_capacity")
        wp = num("wilting_point")
        sat = num("saturation")
        bd = num("bulk_density")
        ksat = num("ksat")
        inf = num("infiltration")
        fc_origin = EvidenceOrigin.MEASURED
        wp_origin = EvidenceOrigin.MEASURED
        sat_origin = EvidenceOrigin.MEASURED
        if fc is None and sand is not None and clay is not None:
            # conservative bounded PTF; labelled, never presented as measured
            fc = max(0.08, min(0.55, 0.2576 - 0.002 * sand + 0.0036 * clay + 0.0299 * (om or 0)))
            fc_origin = EvidenceOrigin.PEDOTRANSFER
        if wp is None and sand is not None and clay is not None:
            wp = max(0.03, min(0.35, 0.026 + 0.005 * clay + 0.0158 * (om or 0)))
            wp_origin = EvidenceOrigin.PEDOTRANSFER
        if sat is None and bd is not None:
            sat = max(0.25, min(0.65, 1 - bd / 2.65))
            sat_origin = EvidenceOrigin.PEDOTRANSFER
        vals = [fc, wp, sat, bd, ksat, inf]
        total += 6
        available += sum(v is not None for v in vals)
        awc = (fc - wp) * (1 - cf / 100) if fc is not None and wp is not None and fc > wp else None
        layers.append(
            SoilHydraulicLayer(
                depth_from_cm=layer.depth_from_cm,
                depth_to_cm=layer.depth_to_cm,
                field_capacity=_hv(
                    fc,
                    "m3/m3",
                    fc_origin,
                    0.75 if fc_origin == EvidenceOrigin.PEDOTRANSFER else 0.95,
                    ids,
                )
                if fc is not None
                else None,
                wilting_point=_hv(
                    wp,
                    "m3/m3",
                    wp_origin,
                    0.75 if wp_origin == EvidenceOrigin.PEDOTRANSFER else 0.95,
                    ids,
                )
                if wp is not None
                else None,
                saturation=_hv(
                    sat,
                    "m3/m3",
                    sat_origin,
                    0.7 if sat_origin == EvidenceOrigin.PEDOTRANSFER else 0.95,
                    ids,
                )
                if sat is not None
                else None,
                available_water_capacity=_hv(awc, "m3/m3", EvidenceOrigin.PEDOTRANSFER, 0.72, ids)
                if awc is not None
                else None,
                bulk_density=_hv(bd, "g/cm3", EvidenceOrigin.MEASURED, 0.9, ids)
                if bd is not None
                else None,
                coarse_fragments=_hv(cf, "%", EvidenceOrigin.MEASURED, 0.8, ids)
                if "coarse_fragments" in p
                else None,
                ksat=_hv(ksat, "mm/h", EvidenceOrigin.MEASURED, 0.9, ids)
                if ksat is not None
                else None,
                infiltration=_hv(inf, "mm/h", EvidenceOrigin.MEASURED, 0.9, ids)
                if inf is not None
                else None,
            )
        )
    score = available / total if total else 0
    executable = all(lay.field_capacity and lay.wilting_point for lay in layers)
    return SoilHydraulicProfile(
        profile_id=f"shp_{uuid4().hex}",
        tenant_id=snapshot.tenant_id or "",
        field_id=snapshot.field_id,
        generated_at=datetime.now(UTC),
        layers=layers,
        completeness_score=round(score, 4),
        executable=executable,
        reasons=[] if executable else ["field_capacity_or_wilting_point_missing"],
        source_soil_profile_hash=snapshot.profile_hash,
    )


def build_water_profile(s: IrrigationWaterSample) -> IrrigationWaterProfile:
    sar = None
    if (
        s.na_meq_l is not None
        and s.ca_meq_l is not None
        and s.mg_meq_l is not None
        and s.ca_meq_l + s.mg_meq_l > 0
    ):
        sar = s.na_meq_l / math.sqrt((s.ca_meq_l + s.mg_meq_l) / 2)
    rsc = None
    if None not in (s.hco3_meq_l, s.ca_meq_l, s.mg_meq_l):
        rsc = (s.co3_meq_l or 0) + s.hco3_meq_l - s.ca_meq_l - s.mg_meq_l
    sal = (
        None
        if s.ecw_ds_m is None
        else ("low" if s.ecw_ds_m < 0.7 else "moderate" if s.ecw_ds_m < 3 else "high")
    )
    sod = (
        None
        if sar is None
        else (
            "low" if sar < 10 else "moderate" if sar < 18 else "high" if sar < 26 else "very_high"
        )
    )
    alk = (
        None
        if rsc is None
        else ("safe" if rsc < 1.25 else "marginal" if rsc <= 2.5 else "unsuitable")
    )
    approved = s.approved and s.ecw_ds_m is not None and sar is not None and rsc is not None
    allowed = ["screening"] + (
        ["crop_selection", "irrigation_planning", "leaching_assessment"] if approved else []
    )
    blocked = (
        []
        if approved
        else ["gypsum_rate", "automatic_irrigation_execution", "reclamation_execution"]
    )
    vals = {
        k: getattr(s, k)
        for k in (
            "ecw_ds_m",
            "ph",
            "na_meq_l",
            "ca_meq_l",
            "mg_meq_l",
            "cl_meq_l",
            "so4_meq_l",
            "hco3_meq_l",
            "co3_meq_l",
            "boron_mg_l",
        )
    }
    return IrrigationWaterProfile(
        profile_id=f"iwp_{uuid4().hex}",
        tenant_id=s.tenant_id,
        field_id=s.field_id,
        source_id=s.source_id,
        effective_at=s.sampled_at,
        sample_id=s.sample_id,
        approval_status="approved" if s.approved else "draft",
        values=vals,
        sar=round(sar, 6) if sar is not None else None,
        rsc_meq_l=round(rsc, 6) if rsc is not None else None,
        salinity_class=sal,
        sodium_class=sod,
        alkalinity_class=alk,
        allowed_use=allowed,
        blocked_use=blocked,
    )

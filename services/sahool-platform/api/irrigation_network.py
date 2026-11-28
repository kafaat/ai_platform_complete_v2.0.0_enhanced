"""api/irrigation_network.py — توأم شبكة الريّ: فحص جدوى التنفيذ (Network Twin، P1)

يمثّل **طوبولوجيا شبكة الريّ** (عُقَد + وصلات موجّهة من المصدر إلى المناطق):
``well → pump → filter → fertilizer → main_line → submain → valve → zone`` — ثمّ يفحص
**جدوى تنفيذ** طلب ريّ عليها **قبل** أيّ تشغيل: هل المنطقة موصولة بمصدر؟ هل ماء البئر
يكفي؟ هل تتجاوز الإنتاجيّة حدّ عقدة ناقلة؟ هل تُلبّى حاجة الضغط؟

**توصية فقط، لا تنفيذ**: يُعلِن الجدوى والاختناقات؛ لا يفتح صمّاماً ولا يشغّل مضخّة.

**نمط الصدق**: الطوبولوجيا والقيود **تُمرَّر** (تُبنى من البنية الحقيقيّة) — لا تُلفَّق.
القيد **الغائب** (سعة/إنتاجيّة/ضغط غير محدَّد) يُعلَن ``unchecked`` ولا يُفترَض نجاحه
(لا «جدوى» كاذبة). ``calibrated`` غير منطبق ⇒ ``not_applicable``.

نقيّ حتميّ (لا قاعدة، لا I/O) — قابل للاختبار offline؛ يستهلكه ``routers/irrigation_network``.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import UTC, timedelta
from itertools import pairwise
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from api.canonical_energy_microgrid_capability import _pv_power_kw

_KINDS = (
    "well",
    "pump",
    "filter",
    "fertilizer",
    "main_line",
    "submain",
    "valve",
    "zone",
)


@dataclass
class NetworkNode:
    """عقدة في شبكة الريّ بقيودها (كلّها اختياريّة — الغائب يُعلَن unchecked)."""

    node_id: str
    kind: str  # well|pump|filter|fertilizer|main_line|submain|valve|zone
    capacity_m3: float | None = None  # بئر: حجم الماء المتاح خلال النافذة
    max_throughput_m3: float | None = None  # عقدة ناقلة: أقصى حجم يمرّ خلال النافذة
    max_pressure_bar: float | None = None  # مضخّة: الضغط الذي توفّره
    min_pressure_bar: float | None = None  # منطقة: الضغط المطلوب
    demand_m3: float | None = None  # منطقة: حجم الماء المطلوب


@dataclass
class NetworkEdge:
    """وصلة موجّهة (من الأعلى نحو المنطقة): from_id ⇒ to_id."""

    from_id: str
    to_id: str


def _trace_to_well(
    zone_id: str, parents: dict[str, list[str]], kinds: dict[str, str]
) -> list[str] | None:
    """يتتبّع أقصر مسار عكسيّ من منطقة إلى أوّل بئر — None إن لا بئر موصول (مقطوعة)."""
    seen = {zone_id}
    queue: deque[tuple[str, list[str]]] = deque([(zone_id, [zone_id])])
    while queue:
        node, path = queue.popleft()
        if kinds.get(node) == "well":
            return path
        for parent in parents.get(node, []):
            if parent not in seen:
                seen.add(parent)
                queue.append((parent, path + [parent]))
    return None


def check_network_feasibility(nodes: list[NetworkNode], edges: list[NetworkEdge]) -> dict:
    """يفحص جدوى تنفيذ طلب الريّ على الشبكة — نقيّ حتميّ، **توصية فقط**.

    لكلّ منطقة (``kind="zone"`` بـ``demand_m3``): يتتبّع مسارها إلى بئر، ثمّ يفحص:
      • **اتّصاليّة**: لا بئر موصول ⇒ infeasible (مقطوعة).
      • **توفّر الماء**: مجموع طلبات مناطق البئر ≤ ``capacity_m3`` (وإلّا عجز).
      • **إنتاجيّة**: طلب يمرّ عبر عقدة ناقلة ذات ``max_throughput_m3`` لا يتجاوزه (وإلّا اختناق).
      • **ضغط**: ``min_pressure_bar`` للمنطقة ≤ ``max_pressure_bar`` لأقرب مضخّة عُلويّة.

    القيد غير المحدَّد يُعلَن ``unchecked`` (لا يُفترَض نجاحه). الناتج: ``zones`` (لكلّ
    منطقة status + reasons + unchecked) + ``overall_feasible`` + ``wells`` (حِمل/سعة) +
    ``warnings_ar`` + ``calibrated=not_applicable``.
    """
    kinds = {n.node_id: (n.kind if n.kind in _KINDS else "submain") for n in nodes}
    by_id = {n.node_id: n for n in nodes}
    parents: dict[str, list[str]] = {}
    for e in edges:
        parents.setdefault(e.to_id, []).append(e.from_id)

    zones = [n for n in nodes if n.kind == "zone"]
    well_load: dict[str, float] = {n.node_id: 0.0 for n in nodes if n.kind == "well"}
    node_load: dict[str, float] = {n.node_id: 0.0 for n in nodes}

    # تمرير ١: مسار كلّ منطقة + تجميع الحِمل على البئر والعُقَد الناقلة.
    paths: dict[str, list[str] | None] = {}
    for z in zones:
        path = _trace_to_well(z.node_id, parents, kinds)
        paths[z.node_id] = path
        demand = max(0.0, z.demand_m3 or 0.0)
        if path:
            for node_id in path:
                node_load[node_id] += demand
            well_id = path[-1]
            well_load[well_id] += demand

    # تمرير ٢: حكم الجدوى لكلّ منطقة.
    out_zones: list[dict] = []
    overall = True
    for z in zones:
        path = paths[z.node_id]
        reasons: list[str] = []
        unchecked: list[str] = []
        bottlenecks: list[str] = []
        demand = max(0.0, z.demand_m3 or 0.0)

        if z.demand_m3 is None:
            unchecked.append("demand")
        if path is None:
            reasons.append("مقطوعة: لا بئر موصول بهذه المنطقة")
            status = "infeasible"
        else:
            well = by_id[path[-1]]
            # توفّر الماء (على مستوى البئر، حِمله الكلّيّ).
            if well.capacity_m3 is None:
                unchecked.append(f"well_capacity:{well.node_id}")
            elif well_load[well.node_id] > well.capacity_m3 + 1e-9:
                reasons.append(
                    f"عجز ماء عند البئر {well.node_id}: الطلب {round(well_load[well.node_id], 1)} > السعة {round(well.capacity_m3, 1)} م³"
                )
                bottlenecks.append(well.node_id)
            # إنتاجيّة العُقَد الناقلة على المسار.
            for node_id in path:
                node = by_id[node_id]
                if node.kind in ("well", "zone"):
                    continue
                if node.max_throughput_m3 is None:
                    unchecked.append(f"throughput:{node_id}")
                elif node_load[node_id] > node.max_throughput_m3 + 1e-9:
                    reasons.append(
                        f"اختناق إنتاجيّة عند {node_id}: المرور {round(node_load[node_id], 1)} > الحدّ {round(node.max_throughput_m3, 1)} م³"
                    )
                    bottlenecks.append(node_id)
            # الضغط: أقرب مضخّة عُلويّة على المسار.
            if z.min_pressure_bar is not None:
                pumps = [by_id[n] for n in path if by_id[n].kind == "pump"]
                pump_press = pumps[0].max_pressure_bar if pumps else None
                if pump_press is None:
                    unchecked.append("pressure")
                elif pump_press + 1e-9 < z.min_pressure_bar:
                    reasons.append(
                        f"نقص ضغط: المطلوب {z.min_pressure_bar} > أقرب مضخّة {pump_press} bar"
                    )
                    bottlenecks.append("pressure")
            status = (
                "infeasible" if reasons else ("feasible_unverified" if unchecked else "feasible")
            )

        if status == "infeasible":
            overall = False
        out_zones.append(
            {
                "zone_id": z.node_id,
                "demand_m3": round(demand, 2),
                "status": status,
                "path": path,
                "reasons_ar": reasons,
                "bottlenecks": list(dict.fromkeys(bottlenecks)),
                "unchecked": unchecked,
            }
        )

    out_wells = [
        {
            "well_id": n.node_id,
            "capacity_m3": round(n.capacity_m3, 2) if n.capacity_m3 is not None else None,
            "load_m3": round(well_load[n.node_id], 2),
            "over_capacity": (
                n.capacity_m3 is not None and well_load[n.node_id] > n.capacity_m3 + 1e-9
            ),
        }
        for n in nodes
        if n.kind == "well"
    ]

    warnings_ar = [
        "فحص جدوى شبكة الريّ — **توصية فقط، لا تنفيذ ولا فتح صمّامات**.",
        "القيد غير المحدَّد يُعلَن unchecked (لا يُفترَض نجاحه) — العتبات تقديريّة غير معايَرة.",
    ]
    disconnected = [z["zone_id"] for z in out_zones if z["path"] is None]
    if disconnected:
        warnings_ar.append("مناطق مقطوعة عن أيّ بئر: " + "، ".join(disconnected))

    return {
        "zones": out_zones,
        "wells": out_wells,
        "overall_feasible": overall,
        "zone_count": len(out_zones),
        "feasible_count": sum(1 for z in out_zones if z["status"] != "infeasible"),
        "calibrated": "not_applicable",
        "thresholds_estimated": True,  # عتبات الجدوى (سعة/إنتاجيّة/ضغط) تقديريّة غير معايَرة
        "warnings_ar": warnings_ar,
    }


Source = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
Rate = Annotated[float, Field(ge=0, le=1e8)]
Positive = Annotated[float, Field(gt=0, le=1e8)]


class PlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PumpingTest(PlanningInput):
    source_ref: Source
    duration_min: Positive
    static_level_m: Rate
    pumping_level_m: Positive
    discharge_m3_h: Positive

    @model_validator(mode="after")
    def positive_drawdown(self):
        if self.pumping_level_m <= self.static_level_m:
            raise ValueError("pumping test requires positive drawdown below static level")
        return self

    def result(self):
        drawdown = self.pumping_level_m - self.static_level_m
        capacity = self.discharge_m3_h / drawdown
        if not math.isfinite(capacity):
            raise ValueError("pumping test outside numeric range")
        return {
            **self.model_dump(),
            "drawdown_m": drawdown,
            "specific_capacity_m3_h_per_m": capacity,
            "sustainable_yield_m3_h": None,
        }


class CurvePoint(PlanningInput):
    flow_m3_h: Rate
    head_m: Positive
    efficiency: float = Field(gt=0, le=1)


class SolarArray(PlanningInput):
    capacity_kwp: Positive
    derate: float = Field(gt=0, le=1)
    temperature_coefficient_per_c: float = Field(ge=-0.02, le=0)


class ScenarioHour(PlanningInput):
    demand_m3: Rate
    well_inflows_m3_h: dict[str, Rate] = Field(max_length=256)
    irradiance_w_m2: float = Field(ge=0, le=1600)
    ambient_temp_c: float = Field(ge=-90, le=70)


class HourlyScenario(PlanningInput):
    source_ref: Source
    start_at: AwareDatetime
    curve: list[CurvePoint] = Field(min_length=2, max_length=128)
    pv: SolarArray
    hours: list[ScenarioHour] = Field(min_length=1, max_length=8784)

    @model_validator(mode="after")
    def validate_profile(self):
        for a, b in pairwise(self.curve):
            if b.flow_m3_h <= a.flow_m3_h or b.head_m > a.head_m:
                raise ValueError("curve needs increasing flow and non-increasing head")
        if self.start_at.year > 9997:
            raise ValueError("simulation start outside timestamp range")
        return self

    def duty_point(self, flow):
        for a, b in pairwise(self.curve):
            if a.flow_m3_h <= flow <= b.flow_m3_h:
                fraction = (flow - a.flow_m3_h) / (b.flow_m3_h - a.flow_m3_h)
                return a.head_m + fraction * (b.head_m - a.head_m), a.efficiency + fraction * (
                    b.efficiency - a.efficiency
                )
        raise ValueError("design duty outside supplied pump curve")


def simulate_hours(req, duty_flow, required_head):
    """Constant in-hour rates. Dispatch only an available fixed-speed duty point."""
    plan = req.hourly_scenario
    if not math.isclose(
        math.fsum(h.demand_m3 for h in plan.hours),
        req.required_gross_volume_m3,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError("hourly demand must sum to required gross volume")
    head, eff = plan.duty_point(duty_flow)
    pump_kw = 9.80665 * (duty_flow / 3600) * head / (eff * req.booster.motor_efficiency)
    if not math.isfinite(pump_kw) or pump_kw <= 0:
        raise ValueError("pump power outside numeric range")
    limits = []
    if head < required_head:
        limits.append("pump_head_below_tdh")
    if duty_flow > req.booster.design_flow_m3_h or (
        req.booster.design_head_m is not None and required_head > req.booster.design_head_m
    ):
        limits.append("booster_design_exceeded")
    if (
        req.booster.installed_motor_power_kw is not None
        and pump_kw > req.booster.installed_motor_power_kw
    ):
        limits.append("motor_power_exceeded")
    wells = {w.well_id: (w.available_flow_m3_h if w.enabled else 0) for w in req.wells}
    tank = req.reservoir
    storage = tank.current_volume_m3
    rows = []
    for index, h in enumerate(plan.hours):
        if h.well_inflows_m3_h.keys() != wells.keys() or any(
            rate > wells[key] for key, rate in h.well_inflows_m3_h.items()
        ):
            raise ValueError(
                "hourly inflows must identify each well and respect its available flow"
            )
        pv_kw = _pv_power_kw(
            irradiance_w_m2=h.irradiance_w_m2,
            ambient_temp_c=h.ambient_temp_c,
            pv_capacity_kwp=plan.pv.capacity_kwp,
            system_derate=plan.pv.derate,
            temperature_coefficient_per_c=plan.pv.temperature_coefficient_per_c,
        )
        inflow = math.fsum(h.well_inflows_m3_h.values())
        available = storage + inflow
        losses = min(available, tank.evaporation_loss_m3_h + tank.seepage_loss_m3_h)
        usable = max(0, available - losses - tank.minimum_operating_volume_m3)
        delivered = min(h.demand_m3, duty_flow, usable) if not limits and pv_kw >= pump_kw else 0.0
        remainder = available - losses - delivered
        spill = max(0, remainder - tank.capacity_m3)
        end = min(tank.capacity_m3, remainder)
        rows.append(
            {
                "at": (plan.start_at.astimezone(UTC) + timedelta(hours=index)).isoformat(),
                "start_storage_m3": storage,
                "inflow_m3": inflow,
                "loss_m3": losses,
                "spill_m3": spill,
                "end_storage_m3": end,
                "demand_m3": h.demand_m3,
                "delivered_m3": delivered,
                "unmet_m3": h.demand_m3 - delivered,
                "pv_kw": pv_kw,
                "energy_used_kwh": pump_kw * (delivered / duty_flow),
            }
        )
        storage = end
    return {
        "basis": "hourly_fixed_duty_planning",
        "status": "unmet_demand" if any(h["unmet_m3"] > 0 for h in rows) else "demand_met",
        "source_ref": plan.source_ref,
        "execution_authorized": False,
        "required_tdh_m": required_head,
        "pump_head_m": head,
        "pump_kw": pump_kw,
        "constraints": limits,
        "hours": rows,
        "unmet_m3": math.fsum(h["unmet_m3"] for h in rows),
        "epanet_duty_inp": epanet_duty_model(req, duty_flow, head),
        "pumping_tests": {w.well_id: w.pumping_test.result() for w in req.wells if w.pumping_test},
    }


def epanet_duty_model(req, flow_m3_h, pump_head_m):
    """EPANET 2.2 input for the serial delivery main at one fixed duty point."""
    previous = req.reservoir.reservoir_id
    visited = {previous}
    elevation = 0.0
    junctions = []
    pipes = []
    for idx, segment in enumerate(req.segments, 1):
        if segment.from_node != previous or segment.to_node in visited:
            raise ValueError("hourly scenario needs one continuous serial main from the reservoir")
        previous = segment.to_node
        visited.add(previous)
        elevation += segment.elevation_change_m
        demand = flow_m3_h / 3.6 if idx == len(req.segments) else 0
        junctions.append(f"J{idx} {elevation:.12g} {demand:.12g}")
        velocity = (flow_m3_h / 3600) / (math.pi * (segment.internal_diameter_mm / 1000) ** 2 / 4)
        loss_k = 2 * 9.80665 * segment.minor_loss_m / velocity**2
        inlet = "R" if idx == 1 else f"J{idx - 1}"
        pipes.append(
            f"P{idx} {inlet} J{idx} {segment.length_m:.12g} {segment.internal_diameter_mm:.12g} {segment.hazen_williams_c:.12g} {loss_k:.12g} OPEN"
        )
    source_head = pump_head_m - req.booster.suction_loss_m
    return "\n".join(
        [
            "[TITLE]",
            "SAHOOL fixed-duty serial delivery main",
            "[JUNCTIONS]",
            *junctions,
            "[RESERVOIRS]",
            f"R {source_head:.12g}",
            "[PIPES]",
            *pipes,
            "[OPTIONS]",
            "UNITS LPS",
            "HEADLOSS H-W",
            "[TIMES]",
            "DURATION 0",
            "[END]",
            "",
        ]
    )

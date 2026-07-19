"""simulation_io.py — فصل الإدخال/الإخراج لمحرّك المحاكاة (SIM-PCSE-01، الشرط ③).

تصميم PCSE يفصل parameters/rate/state عن I/O؛ نعكس ذلك: ``SimulationInputs`` (parameters/weather/soil/
agromanagement مُهيكَلة) → محرّك → ``SimulationOutput`` (yield/biomass/water/stages/**state**). الغراء
(dict↔dataclass · provenance · yield_interval) يبقى في الـadapter. **الغاية:** SIM-GOLDEN-01 يُغذّي
``SimulationInputs`` مباشرةً ويقيس ``SimulationOutput`` مقابل عتبات خطأ مُعلَنة — **يقيس المحرّك لا الغراء**.

وحدة صرفة (لا FastAPI/pcse/قاعدة). مصدر الحقيقة الوحيد لعقد إدخال/إخراج المحاكاة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SimulationInputs:
    """مُدخَل محاكاة مُهيكَل (عقد golden). ``crop_name`` اسم من sim_crop_registry."""

    crop_name: str
    weather: dict[str, Any]
    soil: dict[str, Any]
    agromanagement: dict[str, Any]

    @staticmethod
    def from_dicts(
        crop: dict[str, Any] | None,
        weather: dict[str, Any] | None,
        soil: dict[str, Any] | None,
        agromanagement: dict[str, Any] | None,
    ) -> SimulationInputs:
        c = crop or {}
        name = c.get("name") or c.get("crop") or c.get("crop_name") or ""
        return SimulationInputs(
            crop_name=str(name).strip().lower(),
            weather=weather or {},
            soil=soil or {},
            agromanagement=agromanagement or {},
        )


@dataclass(frozen=True)
class SimulationOutput:
    """مخرَج محاكاة مُهيكَل (عقد golden). ``state`` يحمل المتغيّرات النهائيّة للمقارنة."""

    yield_kg_ha: float
    biomass: float
    water_use: float
    stages: list[dict[str, Any]]
    provenance: str
    state: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "yield_kg_ha": self.yield_kg_ha,
            "biomass": self.biomass,
            "water_use": self.water_use,
            "stages": self.stages,
            "provenance": self.provenance,
            "state": self.state,
            "diagnostics": self.diagnostics,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> SimulationOutput:
        return SimulationOutput(
            yield_kg_ha=float(d.get("yield_kg_ha", 0.0)),
            biomass=float(d.get("biomass", 0.0)),
            water_use=float(d.get("water_use", 0.0)),
            stages=list(d.get("stages", []) or []),
            provenance=str(d.get("provenance", "")),
            state=dict(d.get("state", {}) or {}),
            diagnostics=dict(d.get("diagnostics", {}) or {}),
        )

"""compliance_engine.py — محرّك المطابقة بالأدلّة (Farmland Phase 2 · 0001).

يقيّم ملاحظات مقيسة مقابل بنود المعايير في `standards_registry` ويُرجِع لكلّ بند
**pass / fail / not_evaluated** مع الدليل الكامل (القيمة، الوحدة، الحدّ، مرجع البند
والإصدار، المصدر، تاريخ القياس).

قواعد الصدق (fail-closed):
- **لا مطابقة على غياب.** بندٌ بلا ملاحظة ⇒ `not_evaluated` (`missing_observation`)،
  ولا يرتفع الحكم الإجماليّ إلى `compliant` ما دام بندٌ واحد غير مُقيَّم.
- **لا تحويل وحدات صامت.** وحدة الملاحظة ≠ وحدة البند ⇒ `not_evaluated` (`unit_mismatch`).
- **لا قيمة غير منتهية.** NaN/inf/غير رقميّ ⇒ `not_evaluated` (`non_finite_value`).
- **الحداثة.** بندٌ له `max_age_days` وقياسٌ أقدم منه أو بلا تاريخ ⇒ `not_evaluated`.
- **سياق التطبيق.** بندٌ له `applies_to` لا يُقيَّم إلّا إذا طلبه المستدعي صراحةً في
  `contexts`؛ وإلّا يُدرَج `not_applicable` (لا يُحسَب في الحكم ولا يُخفى من الناتج).

الحكم الإجماليّ: `non_compliant` إن فشل أيّ بند؛ وإلّا `incomplete` إن بقي بندٌ غير مُقيَّم؛
وإلّا `compliant`. نقيّ بالكامل (بلا I/O).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from standards_registry import Clause, Standard, StandardsRegistry

ENGINE_VERSION = "compliance-engine.v1"


@dataclass(frozen=True)
class Observation:
    """ملاحظة مقيسة واحدة — مصدرها وتاريخها جزء من الدليل لا تفصيل اختياريّ."""

    parameter: str
    value: float
    unit: str
    source: str
    observed_on: date | None = None
    method: str = ""


@dataclass
class ClauseResult:
    standard_ref: str
    clause_id: str
    parameter: str
    status: str  # pass | fail | not_evaluated | not_applicable
    reason: str
    evidence: dict = field(default_factory=dict)
    band: str | None = None

    def to_dict(self) -> dict:
        out = {
            "standard": self.standard_ref,
            "clause": self.clause_id,
            "parameter": self.parameter,
            "status": self.status,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }
        if self.band is not None:
            out["band"] = self.band
        return out


@dataclass
class ComplianceReport:
    verdict: str  # compliant | non_compliant | incomplete
    evaluated_on: date
    results: list[ClauseResult]
    profile_id: str | None = None
    engine_version: str = ENGINE_VERSION

    @property
    def counts(self) -> dict[str, int]:
        out = {"pass": 0, "fail": 0, "not_evaluated": 0, "not_applicable": 0}
        for r in self.results:
            out[r.status] += 1
        return out

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "evaluated_on": self.evaluated_on.isoformat(),
            "profile_id": self.profile_id,
            "engine_version": self.engine_version,
            "counts": self.counts,
            "results": [r.to_dict() for r in self.results],
        }


def _is_finite_number(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def classify_band(clause: Clause, value: float) -> str | None:
    """الشريحة التي تقع فيها القيمة ([lower, upper)) أو None إن خرجت عن الشرائح."""
    if clause.limit_kind != "bands" or not _is_finite_number(value):
        return None
    for band in clause.bands:
        if value >= band.lower and (band.upper is None or value < band.upper):
            return band.label
    return None


def evaluate_clause(
    standard: Standard,
    clause: Clause,
    observation: Observation | None,
    *,
    on: date,
    contexts: frozenset[str] = frozenset(),
) -> ClauseResult:
    base = {
        "standard_ref": standard.ref,
        "clause_id": clause.clause_id,
        "parameter": clause.parameter,
    }
    limit = {
        "limit_kind": clause.limit_kind,
        "lower": clause.lower,
        "upper": clause.upper,
        "upper_inclusive": clause.upper_inclusive,
        "unit": clause.unit,
        "source": clause.source,
        "calibrated_for_region": clause.calibrated_for_region,
    }
    if clause.limit_kind == "bands":
        limit["bands"] = [[b.label, b.lower, b.upper] for b in clause.bands]
        limit["pass_labels"] = list(clause.pass_labels)

    if clause.applies_to and clause.applies_to not in contexts:
        return ClauseResult(
            **base,
            status="not_applicable",
            reason=f"context_not_requested:{clause.applies_to}",
            evidence={"limit": limit},
        )
    if observation is None:
        return ClauseResult(
            **base, status="not_evaluated", reason="missing_observation", evidence={"limit": limit}
        )

    evidence = {
        "limit": limit,
        "observed": {
            "value": observation.value,
            "unit": observation.unit,
            "source": observation.source,
            "observed_on": observation.observed_on.isoformat() if observation.observed_on else None,
            "method": observation.method,
        },
    }
    if not _is_finite_number(observation.value):
        return ClauseResult(
            **base, status="not_evaluated", reason="non_finite_value", evidence=evidence
        )
    if observation.unit.strip() != clause.unit:
        return ClauseResult(
            **base, status="not_evaluated", reason="unit_mismatch", evidence=evidence
        )
    if clause.max_age_days is not None:
        if observation.observed_on is None:
            return ClauseResult(
                **base, status="not_evaluated", reason="observation_date_missing", evidence=evidence
            )
        age = (on - observation.observed_on).days
        evidence["observed"]["age_days"] = age
        if age < 0:
            return ClauseResult(
                **base, status="not_evaluated", reason="observation_in_future", evidence=evidence
            )
        if age > clause.max_age_days:
            return ClauseResult(
                **base, status="not_evaluated", reason="observation_stale", evidence=evidence
            )

    value = float(observation.value)
    if clause.limit_kind == "bands":
        band = classify_band(clause, value)
        if band is None:
            return ClauseResult(
                **base, status="not_evaluated", reason="outside_bands", evidence=evidence
            )
        ok = band in clause.pass_labels
        return ClauseResult(
            **base,
            status="pass" if ok else "fail",
            reason=f"band:{band}",
            evidence=evidence,
            band=band,
        )
    below_upper = (
        clause.upper is None
        or value < clause.upper
        or (clause.upper_inclusive and value == clause.upper)
    )
    if clause.limit_kind == "max":
        ok = below_upper
        op = "<=" if clause.upper_inclusive else "<"
        reason = f"{value} {op if ok else 'violates ' + op} {clause.upper}"
    elif clause.limit_kind == "min":
        ok = value >= clause.lower
        reason = f"{value} {'>=' if ok else '<'} {clause.lower}"
    else:  # range
        ok = clause.lower <= value and below_upper
        close = "]" if clause.upper_inclusive else ")"
        reason = f"{value} {'in' if ok else 'outside'} [{clause.lower}, {clause.upper}{close}"
    return ClauseResult(**base, status="pass" if ok else "fail", reason=reason, evidence=evidence)


def evaluate_standards(
    standards: list[Standard],
    observations: list[Observation],
    *,
    on: date | None = None,
    contexts: frozenset[str] | set[str] = frozenset(),
    profile_id: str | None = None,
) -> ComplianceReport:
    """يقيّم كلّ بند في المعايير المعطاة. ملاحظتان للمعامل نفسه ⇒ خطأ صريح لا اختيار صامت."""
    on = on or date.today()
    contexts = frozenset(contexts)
    by_param: dict[str, Observation] = {}
    for obs in observations:
        if obs.parameter in by_param:
            raise ValueError(f"duplicate_observation:{obs.parameter}")
        by_param[obs.parameter] = obs
    results = [
        evaluate_clause(s, c, by_param.get(c.parameter), on=on, contexts=contexts)
        for s in standards
        for c in s.clauses
    ]
    statuses = {r.status for r in results}
    if "fail" in statuses:
        verdict = "non_compliant"
    elif "not_evaluated" in statuses or not (statuses - {"not_applicable"}):
        verdict = "incomplete"
    else:
        verdict = "compliant"
    return ComplianceReport(
        verdict=verdict, evaluated_on=on, results=results, profile_id=profile_id
    )


def evaluate_profile(
    registry: StandardsRegistry,
    profile_id: str,
    observations: list[Observation],
    *,
    on: date | None = None,
    contexts: frozenset[str] | set[str] = frozenset(),
) -> ComplianceReport:
    """يقيّم الملاحظات مقابل معايير ملفّ الاعتماد بإصداراتها السارية وتشديداتها."""
    on = on or date.today()
    standards = registry.profile_standards(profile_id, on)
    return evaluate_standards(
        standards, observations, on=on, contexts=contexts, profile_id=profile_id
    )

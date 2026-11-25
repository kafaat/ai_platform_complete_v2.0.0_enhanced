"""standards_registry.py — سجلّ المعايير الفنّيّة المُصدَّر (Farmland Phase 2 · 0001).

سجلّ نقيّ (بلا I/O) لمعايير التربة ومياه الريّ التي تقيس عليها الخدمة: لكلّ معيار
**مُعرِّف + إصدار + تاريخ سريان + حالة** (active / superseded / withdrawn) ومصدر مكتوب،
ولكلّ بند **معامل + وحدة + نوع حدّ + طريقة قياس + مرجع البند في المصدر**.

القرارات الصادقة:
- **لا قيمة بلا مصدر.** كلّ بند يحمل `source` يُسمّي الجدول/الصفحة في الوثيقة الأصليّة.
  البنود المأخوذة من أدبيّات عامّة لا معايرة يمنيّة تحمل `calibrated_for_region=False`.
- **الإصدار لا يُستبدَل بصمت.** طلب معيارٍ بلا إصدار يُرجِع الإصدار **الساري في التاريخ
  المطلوب**؛ الإصدار المُستبدَل يبقى قابلاً للاستعلام صراحةً (للتدقيق التاريخيّ) ويحمل
  `superseded_by`؛ والمسحوب (`withdrawn`) لا يُرجَع ساريّاً أبداً.
- **الصلاحية ≠ الاعتماد المحلّيّ.** حالة المعيار (active/superseded/withdrawn) تقول هل هو
  ساري المفعول عند مُصدِره؛ أمّا **اعتماده** في دولة/مشروع فقرارٌ منفصل يُسجَّل في ملفّ
  الاعتماد (`adopted` / `provisional` / `reference_only`) بجهةٍ ومرجع. الافتراضيّ
  `reference_only`: مطابقةٌ فنّيّة لمرجعٍ أدبيّ، لا امتثالٌ لحدٍّ ملزم.
- **ملفّات الاعتماد (profiles)** حسب الدولة/المنطقة/المشروع تختار المعايير وإصداراتها،
  وتسمح **بالتشديد فقط**: تجاوزٌ يُرخي حدّاً (يرفع حدّاً أعلى أو يخفض حدّاً أدنى) يُرفَض
  عند البناء — مشروعٌ لا يستطيع أن «يُطابق» بتليين المعيار.

المعادلات والمطابقة نفسها في `compliance_engine.py`؛ هذا الملفّ بيانات وحلّ إصدارات فقط.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

REGISTRY_VERSION = "farmland-standards.v1"

# draft = مسودة لم يثبت نشرها النهائيّ · unresolved = إصدار مثبت وسريانه غير محسوم بالدليل.
_STATUSES = ("active", "superseded", "withdrawn", "draft", "unresolved")
# لا يظهر أيٌّ منها التزاماً نافذاً — لا عبر current() ولا عبر تثبيتٍ في ملفّ اعتماد.
_NEVER_IN_FORCE = frozenset({"withdrawn", "draft", "unresolved"})
NEVER_IN_FORCE = _NEVER_IN_FORCE
ADOPTION_STATUSES = ("adopted", "provisional", "reference_only")
_LIMIT_KINDS = ("max", "min", "range", "bands")


class StandardsRegistryError(ValueError):
    """خطأ بنية/حلّ في السجلّ — يُرفَع بدل إرجاع قيمة مُخمَّنة."""


@dataclass(frozen=True)
class Band:
    """شريحة تصنيف مرتّبة: [lower, upper) — `upper=None` مفتوح من الأعلى."""

    label: str
    lower: float
    upper: float | None


@dataclass(frozen=True)
class Clause:
    """بند قابل للتقييم في معيار.

    limit_kind:
      max    القيمة ≤ upper تطابق.
      min    القيمة ≥ lower تطابق.
      range  lower ≤ القيمة ≤ upper تطابق.
      bands  تصنيف بشرائح مرتّبة؛ `pass_labels` تحدّد الشرائح المطابِقة.
    """

    clause_id: str
    parameter: str
    unit: str
    limit_kind: str
    title_ar: str
    source: str
    lower: float | None = None
    upper: float | None = None
    bands: tuple[Band, ...] = ()
    pass_labels: tuple[str, ...] = ()
    measurement_method: str = ""
    applies_to: str = ""  # سياق تطبيق البند (مثلاً «surface_irrigation»)؛ فارغ = عامّ
    max_age_days: int | None = None  # أقصى عمر للقياس ليُعتمَد؛ None = بلا قيد زمنيّ
    calibrated_for_region: bool = False
    # هل يطابق الحدّ الأعلى نفسه؟ True ⇒ «≤ upper». False ⇒ «< upper» — حين يُعرِّف المصدر
    # الصنفَ المرفوض بـ«≥ upper» (HB60: ملحيّة عند ECe ≥ 4، صوديّة عند ESP ≥ 15).
    upper_inclusive: bool = True


@dataclass(frozen=True)
class Standard:
    standard_id: str
    version: str
    title: str
    issuer: str
    effective_from: date | None  # None مسموح فقط لغير الساري (تاريخ نفاذ لم يُثبَت)
    status: str
    clauses: tuple[Clause, ...]
    superseded_by: str | None = None  # "standard_id@version"
    effective_to: date | None = None
    kind: str = "standard"
    jurisdiction: str = ""
    sources: tuple[str, ...] = ()
    # أثر التدقيق الذي جاء منه الإصدار (كتالوج، رقم السطر، نصّ التحقّق والتصحيح…).
    audit: dict | None = field(default=None, compare=False, hash=False)

    @property
    def ref(self) -> str:
        return f"{self.standard_id}@{self.version}"

    def clause(self, clause_id: str) -> Clause:
        for c in self.clauses:
            if c.clause_id == clause_id:
                return c
        raise StandardsRegistryError(f"unknown_clause:{self.ref}:{clause_id}")


@dataclass(frozen=True)
class ClauseOverride:
    """تشديد بند داخل ملفّ اعتماد — سبب مكتوب إلزاميّ."""

    standard_id: str
    clause_id: str
    reason: str
    lower: float | None = None
    upper: float | None = None


@dataclass(frozen=True)
class StandardAdoption:
    """قرار اعتماد معيارٍ محلّيّاً — مستقلّ عن صلاحيّته عند مُصدِره.

    `adopted` و`provisional` يتطلّبان جهةً (`authority`) ومرجعاً مكتوباً (`reference`: قرار،
    لائحة، محضر) — لا ادّعاء اعتمادٍ بلا مصدر. غياب السجلّ ⇒ `reference_only`.
    """

    standard_id: str
    status: str
    authority: str = ""
    reference: str = ""
    adopted_on: date | None = None


@dataclass(frozen=True)
class ComplianceProfile:
    profile_id: str
    country: str
    standards: tuple[str, ...]  # "standard_id" (الساري) أو "standard_id@version" (مُثبَّت)
    region: str | None = None
    project: str | None = None
    overrides: tuple[ClauseOverride, ...] = ()
    adoption: tuple[StandardAdoption, ...] = ()
    notes: str = ""


@dataclass
class StandardsRegistry:
    """فهرس المعايير بإصداراتها + ملفّات الاعتماد."""

    standards: dict[tuple[str, str], Standard] = field(default_factory=dict)
    profiles: dict[str, ComplianceProfile] = field(default_factory=dict)

    # ── التسجيل ─────────────────────────────────────────────────────────
    def register(self, standard: Standard) -> None:
        _validate_standard(standard)
        key = (standard.standard_id, standard.version)
        if key in self.standards:
            raise StandardsRegistryError(f"duplicate_standard_version:{standard.ref}")
        self.standards[key] = standard

    def register_profile(self, profile: ComplianceProfile) -> None:
        if profile.profile_id in self.profiles:
            raise StandardsRegistryError(f"duplicate_profile:{profile.profile_id}")
        # يتحقّق أنّ كلّ مرجع يُحلّ وأنّ كلّ تجاوز تشديدٌ لا إرخاء — عند البناء لا عند الاستعمال.
        for override in profile.overrides:
            standard = self._resolve_ref_for_override(profile, override.standard_id)
            _validate_override(standard.clause(override.clause_id), override)
        for ref in profile.standards:
            self.resolve(ref)
        listed = {ref.split("@", 1)[0] for ref in profile.standards}
        seen: set[str] = set()
        for a in profile.adoption:
            if a.standard_id not in listed:
                raise StandardsRegistryError(f"adoption_targets_unlisted_standard:{a.standard_id}")
            if a.standard_id in seen:
                raise StandardsRegistryError(f"duplicate_adoption:{a.standard_id}")
            seen.add(a.standard_id)
            if a.status not in ADOPTION_STATUSES:
                raise StandardsRegistryError(f"unknown_adoption_status:{a.standard_id}:{a.status}")
            if a.status != "reference_only" and not (a.authority.strip() and a.reference.strip()):
                raise StandardsRegistryError(
                    f"adoption_without_authority_or_reference:{a.standard_id}"
                )
        self.profiles[profile.profile_id] = profile

    # ── الحلّ ───────────────────────────────────────────────────────────
    def versions(self, standard_id: str) -> list[Standard]:
        out = [s for (sid, _), s in self.standards.items() if sid == standard_id]
        if not out:
            raise StandardsRegistryError(f"unknown_standard:{standard_id}")
        return sorted(out, key=lambda s: s.effective_from or date.min)

    def get(self, standard_id: str, version: str) -> Standard:
        """إصدار محدّد صراحةً — يشمل المُستبدَل (للتدقيق التاريخيّ)."""
        try:
            return self.standards[(standard_id, version)]
        except KeyError:
            raise StandardsRegistryError(
                f"unknown_standard_version:{standard_id}@{version}"
            ) from None

    def current(self, standard_id: str, on: date | None = None) -> Standard:
        """الإصدار الساري في التاريخ `on` (افتراضيّاً اليوم).

        الساري = حالته ليست withdrawn/draft/unresolved، وله تاريخ نفاذ، وبدأ سريانه في `on` أو قبله، ولم ينتهِ قبله؛ وعند تعدّد
        المرشّحين يفوز الأحدث سرياناً. لا مرشّح ⇒ خطأ صريح لا ارتداد إلى أقدم إصدار.
        """
        on = on or date.today()
        candidates = [
            s
            for s in self.versions(standard_id)
            if s.status not in _NEVER_IN_FORCE
            and s.effective_from is not None
            and s.effective_from <= on
            and (s.effective_to is None or on < s.effective_to)
        ]
        if not candidates:
            raise StandardsRegistryError(f"no_effective_version:{standard_id}@{on.isoformat()}")
        return max(candidates, key=lambda s: s.effective_from)

    def resolve(self, ref: str, on: date | None = None) -> Standard:
        """«id» ⇒ الساري؛ «id@version» ⇒ ذلك الإصدار.

        المثبَّت المسحوب/المسوَّدة/غير المحسوم يُرفَض؛ والمثبَّت الذي لم يبدأ نفاذه في `on` يُرفَض
        (إصدار مستقبليّ لا يُقدَّم التزاماً نافذاً). `on` الغائب = اليوم بتقويم المضيف (UTC في
        النشر) — فتسجيل ملفّ اعتمادٍ يثبّت إصداراً مستقبليّاً يُرفَض اليوم أيضاً. `get()` يبقى
        متاحاً للتدقيق التاريخيّ.
        """
        on = on or date.today()
        if "@" in ref:
            sid, version = ref.split("@", 1)
            standard = self.get(sid, version)
            if standard.status in _NEVER_IN_FORCE:
                raise StandardsRegistryError(f"{standard.status}_standard:{standard.ref}")
            if (
                on is not None
                and standard.effective_from is not None
                and on < standard.effective_from
            ):
                raise StandardsRegistryError(f"not_yet_effective:{standard.ref}@{on.isoformat()}")
            return standard
        return self.current(ref, on)

    def supersession_chain(self, standard_id: str, version: str) -> list[str]:
        """سلسلة الاستبدال من إصدار إلى أحدث خلَف له (تكشف الحلقات بدل الدوران)."""
        chain = [f"{standard_id}@{version}"]
        seen = set(chain)
        standard = self.get(standard_id, version)
        while standard.superseded_by:
            nxt = standard.superseded_by
            if nxt in seen:
                raise StandardsRegistryError(f"supersession_cycle:{nxt}")
            seen.add(nxt)
            chain.append(nxt)
            sid, ver = nxt.split("@", 1)
            standard = self.get(sid, ver)
        return chain

    def adoption_status(self, profile_id: str, standard_id: str) -> StandardAdoption:
        """قرار الاعتماد المحلّيّ للمعيار في الملفّ؛ غيابه ⇒ `reference_only` صريحاً."""
        try:
            profile = self.profiles[profile_id]
        except KeyError:
            raise StandardsRegistryError(f"unknown_profile:{profile_id}") from None
        for a in profile.adoption:
            if a.standard_id == standard_id:
                return a
        return StandardAdoption(standard_id, "reference_only")

    def profile_standards(self, profile_id: str, on: date | None = None) -> list[Standard]:
        """معايير الملفّ بعد الحلّ وتطبيق التجاوزات (التشديدات) على بنودها."""
        try:
            profile = self.profiles[profile_id]
        except KeyError:
            raise StandardsRegistryError(f"unknown_profile:{profile_id}") from None
        out = []
        for ref in profile.standards:
            standard = self.resolve(ref, on)
            mine = [o for o in profile.overrides if o.standard_id == standard.standard_id]
            if mine:
                by_clause = {o.clause_id: o for o in mine}
                clauses = []
                for c in standard.clauses:
                    o = by_clause.get(c.clause_id)
                    if o is None:
                        clauses.append(c)
                        continue
                    _validate_override(c, o)
                    clauses.append(
                        replace(
                            c,
                            lower=c.lower if o.lower is None else o.lower,
                            upper=c.upper if o.upper is None else o.upper,
                            source=f"{c.source} · tightened by profile {profile_id}: {o.reason}",
                        )
                    )
                standard = replace(standard, clauses=tuple(clauses))
            out.append(standard)
        return out

    def _resolve_ref_for_override(self, profile: ComplianceProfile, standard_id: str) -> Standard:
        for ref in profile.standards:
            if ref.split("@", 1)[0] == standard_id:
                return self.resolve(ref)
        raise StandardsRegistryError(f"override_targets_unlisted_standard:{standard_id}")


# ── التحقّق البنيويّ ──────────────────────────────────────────────────────


def _finite(x: float | None) -> bool:
    return (
        x is not None
        and not isinstance(x, bool)
        and isinstance(x, (int, float))
        and math.isfinite(x)
    )


def _validate_clause(c: Clause, ref: str) -> None:
    where = f"{ref}:{c.clause_id}"
    if c.limit_kind not in _LIMIT_KINDS:
        raise StandardsRegistryError(f"unknown_limit_kind:{where}:{c.limit_kind}")
    if not c.source.strip():
        raise StandardsRegistryError(f"clause_without_source:{where}")
    if not c.unit.strip():
        raise StandardsRegistryError(f"clause_without_unit:{where}")
    if c.limit_kind == "max" and not _finite(c.upper):
        raise StandardsRegistryError(f"max_clause_needs_upper:{where}")
    if c.limit_kind == "min" and not _finite(c.lower):
        raise StandardsRegistryError(f"min_clause_needs_lower:{where}")
    if c.limit_kind == "range":
        if not (_finite(c.lower) and _finite(c.upper)) or c.lower > c.upper:
            raise StandardsRegistryError(f"range_clause_needs_ordered_bounds:{where}")
    if c.limit_kind == "bands":
        if not c.bands:
            raise StandardsRegistryError(f"bands_clause_needs_bands:{where}")
        prev_upper: float | None = None
        for i, b in enumerate(c.bands):
            if not _finite(b.lower):
                raise StandardsRegistryError(f"band_lower_not_finite:{where}:{b.label}")
            if prev_upper is not None and b.lower != prev_upper:
                raise StandardsRegistryError(f"bands_not_contiguous:{where}:{b.label}")
            if b.upper is None and i != len(c.bands) - 1:
                raise StandardsRegistryError(f"open_band_not_last:{where}:{b.label}")
            if b.upper is not None and (not _finite(b.upper) or b.upper <= b.lower):
                raise StandardsRegistryError(f"band_bounds_invalid:{where}:{b.label}")
            prev_upper = b.upper
        labels = {b.label for b in c.bands}
        if not c.pass_labels or not set(c.pass_labels) <= labels:
            raise StandardsRegistryError(f"bands_pass_labels_invalid:{where}")


def _validate_standard(s: Standard) -> None:
    if s.status not in _STATUSES:
        raise StandardsRegistryError(f"unknown_status:{s.ref}:{s.status}")
    if s.status == "superseded" and not s.superseded_by:
        raise StandardsRegistryError(f"superseded_without_successor:{s.ref}")
    if s.effective_from is None and s.status not in _NEVER_IN_FORCE:
        raise StandardsRegistryError(f"in_force_status_needs_effective_date:{s.ref}")
    if (
        s.effective_to is not None
        and s.effective_from is not None
        and s.effective_to <= s.effective_from
    ):
        raise StandardsRegistryError(f"effective_window_inverted:{s.ref}")
    ids = [c.clause_id for c in s.clauses]
    if len(ids) != len(set(ids)):
        raise StandardsRegistryError(f"duplicate_clause_id:{s.ref}")
    for c in s.clauses:
        _validate_clause(c, s.ref)


def _validate_override(c: Clause, o: ClauseOverride) -> None:
    """التشديد فقط: الحدّ الأعلى لا يرتفع، والأدنى لا ينخفض، والمدى لا يتّسع."""
    where = f"{o.standard_id}:{o.clause_id}"
    if not o.reason.strip():
        raise StandardsRegistryError(f"override_without_reason:{where}")
    if c.limit_kind == "bands":
        raise StandardsRegistryError(f"bands_clause_not_overridable:{where}")
    if o.lower is None and o.upper is None:
        raise StandardsRegistryError(f"override_changes_nothing:{where}")
    if o.upper is not None:
        if c.limit_kind == "min" or not _finite(o.upper) or o.upper > c.upper:
            raise StandardsRegistryError(f"override_loosens_upper:{where}")
    if o.lower is not None:
        if c.limit_kind == "max" or not _finite(o.lower) or o.lower < c.lower:
            raise StandardsRegistryError(f"override_loosens_lower:{where}")
    lower = c.lower if o.lower is None else o.lower
    upper = c.upper if o.upper is None else o.upper
    if lower is not None and upper is not None and lower > upper:
        raise StandardsRegistryError(f"override_inverts_range:{where}")


# ── المعايير المُصدَّرة (قيم أدبيّة موثَّقة فقط — لا قيم مُختلَقة) ───────────────

_FAO29 = "FAO Irrigation and Drainage Paper 29 Rev.1 (Ayers & Westcot, 1985), Table 1"
_HB60 = "USDA Agriculture Handbook 60 (Richards, ed., 1954), Ch. 1 & 4"
AH210_SOURCE = _AH210 = (
    "USDA Agriculture Handbook 210 (Klingebiel & Montgomery, 1961) — limiting-factor "
    "land capability concept; numeric class limits are INDICATIVE (AH-210 publishes none "
    "nationally) and must be calibrated by the regional guide"
)

FAO29_WATER_QUALITY = Standard(
    standard_id="FAO-29",
    version="rev1-1985",
    title="Water quality for agriculture — guidelines for interpretation of water quality for irrigation",
    issuer="FAO",
    effective_from=date(1985, 1, 1),
    status="active",
    clauses=(
        Clause(
            clause_id="T1.salinity.ECw",
            parameter="ecw_ds_m",
            unit="dS/m",
            limit_kind="bands",
            title_ar="ملوحة مياه الريّ (ECw) — درجة القيد على الاستعمال",
            source=f"{_FAO29} — Salinity (affects crop water availability), ECw",
            bands=(
                Band("none", 0.0, 0.7),
                Band("slight_to_moderate", 0.7, 3.0),
                Band("severe", 3.0, None),
            ),
            pass_labels=("none",),
            measurement_method="EC of irrigation water at 25 °C",
            max_age_days=365,
        ),
        Clause(
            clause_id="T1.sodium.SAR.surface",
            parameter="sar",
            unit="(mmol/L)^0.5",
            limit_kind="bands",
            title_ar="سمّيّة الصوديوم — الريّ السطحيّ (SAR)",
            source=f"{_FAO29} — Specific ion toxicity, Sodium (Na), surface irrigation",
            bands=(
                Band("none", 0.0, 3.0),
                Band("slight_to_moderate", 3.0, 9.0),
                Band("severe", 9.0, None),
            ),
            pass_labels=("none",),
            applies_to="surface_irrigation",
            max_age_days=365,
        ),
        Clause(
            clause_id="T1.chloride.surface",
            parameter="cl_meq_l",
            unit="meq/L",
            limit_kind="bands",
            title_ar="سمّيّة الكلوريد — الريّ السطحيّ",
            source=f"{_FAO29} — Specific ion toxicity, Chloride (Cl), surface irrigation",
            bands=(
                Band("none", 0.0, 4.0),
                Band("slight_to_moderate", 4.0, 10.0),
                Band("severe", 10.0, None),
            ),
            pass_labels=("none",),
            applies_to="surface_irrigation",
            max_age_days=365,
        ),
        Clause(
            clause_id="T1.boron",
            parameter="b_mg_l",
            unit="mg/L",
            limit_kind="bands",
            title_ar="سمّيّة البورون",
            source=f"{_FAO29} — Specific ion toxicity, Boron (B)",
            bands=(
                Band("none", 0.0, 0.7),
                Band("slight_to_moderate", 0.7, 3.0),
                Band("severe", 3.0, None),
            ),
            pass_labels=("none",),
            max_age_days=365,
        ),
        Clause(
            clause_id="T1.pH",
            parameter="ph",
            unit="pH",
            limit_kind="range",
            title_ar="pH مياه الريّ — المدى الطبيعيّ",
            source=f"{_FAO29} — Miscellaneous effects, pH normal range 6.5–8.4",
            lower=6.5,
            upper=8.4,
            max_age_days=365,
        ),
    ),
)

HB60_SALINE_SODIC = Standard(
    standard_id="USDA-HB60",
    version="1954",
    title="Diagnosis and improvement of saline and alkali soils",
    issuer="USDA Salinity Laboratory",
    effective_from=date(1954, 1, 1),
    status="active",
    clauses=(
        Clause(
            clause_id="saline.ECe",
            parameter="ece_ds_m",
            unit="dS/m",
            limit_kind="max",
            title_ar="ملوحة مستخلص العجينة المشبعة (ECe) — دون حدّ التربة الملحيّة",
            source=f"{_HB60} — saline soil: ECe ≥ 4 dS/m at 25 °C",
            upper=4.0,
            upper_inclusive=False,
            measurement_method="EC of saturated-paste extract at 25 °C",
            max_age_days=730,
        ),
        Clause(
            clause_id="sodic.ESP",
            parameter="esp_pct",
            unit="%",
            limit_kind="max",
            title_ar="نسبة الصوديوم المتبادل (ESP) — دون حدّ التربة الصوديّة",
            source=f"{_HB60} — sodic (alkali) soil: ESP ≥ 15",
            upper=15.0,
            upper_inclusive=False,
            measurement_method="exchangeable Na / CEC × 100",
            max_age_days=730,
        ),
    ),
)

AH210_LAND_CAPABILITY = Standard(
    standard_id="USDA-AH210-INDICATIVE",
    version="v1",
    title="Land capability classification — indicative limiting-factor class limits",
    issuer="USDA SCS concept; SAHOOL indicative limits",
    effective_from=date(1961, 1, 1),
    status="active",
    clauses=(
        Clause(
            clause_id="slope",
            parameter="slope_pct",
            unit="%",
            limit_kind="bands",
            title_ar="الانحدار — صنف القدرة",
            source=_AH210,
            bands=(
                Band("I", 0.0, 2.0),
                Band("II", 2.0, 6.0),
                Band("III", 6.0, 12.0),
                Band("IV", 12.0, 18.0),
                Band("VI", 18.0, 30.0),
                Band("VII", 30.0, 50.0),
                Band("VIII", 50.0, None),
            ),
            pass_labels=("I", "II", "III", "IV"),
        ),
        Clause(
            clause_id="ece",
            parameter="ece_ds_m",
            unit="dS/m",
            limit_kind="bands",
            title_ar="ملوحة التربة — صنف القدرة",
            source=f"{_AH210}; salinity steps follow HB60 (2/4/8/16 dS/m)",
            bands=(
                Band("I", 0.0, 2.0),
                Band("II", 2.0, 4.0),
                Band("III", 4.0, 8.0),
                Band("IV", 8.0, 16.0),
                Band("VI", 16.0, None),
            ),
            pass_labels=("I", "II", "III", "IV"),
        ),
        Clause(
            clause_id="esp",
            parameter="esp_pct",
            unit="%",
            limit_kind="bands",
            title_ar="الصوديّة — صنف القدرة",
            source=f"{_AH210}; HB60 sodic threshold ESP 15 marks the class III/IV step",
            bands=(
                Band("I", 0.0, 5.0),
                Band("II", 5.0, 10.0),
                Band("III", 10.0, 15.0),
                Band("IV", 15.0, 25.0),
                Band("VI", 25.0, None),
            ),
            pass_labels=("I", "II", "III", "IV"),
        ),
    ),
)

# العمق الفعّال يُصنَّف تنازليّاً (الأعمق أفضل) فلا يناسب شرائح تصاعديّة بتسميات مرتّبة؛
# حدوده هنا ثوابت مُعلَنة يستهلكها `land_quality.land_capability` (المصدر نفسه، إرشاديّة).
EFFECTIVE_DEPTH_CLASS_LIMITS_CM: tuple[tuple[str, float], ...] = (
    ("I", 100.0),
    ("II", 75.0),
    ("III", 50.0),
    ("IV", 25.0),
    ("VI", 15.0),
)
DRAINAGE_CLASS_TO_CAPABILITY: dict[str, str] = {
    "well": "I",
    "moderately_well": "II",
    "somewhat_poor": "III",
    "poor": "IV",
    "very_poor": "V",
}

YEMEN_DEFAULT_PROFILE = ComplianceProfile(
    profile_id="YE-default",
    country="YE",
    standards=("FAO-29", "USDA-HB60", "USDA-AH210-INDICATIVE"),
    notes=(
        "Literature defaults; no Yemeni national standard is registered yet. Regional "
        "calibration is required before any clause is treated as a legal limit."
    ),
)


def default_registry() -> StandardsRegistry:
    """سجلّ جديد بالمعايير المُصدَّرة وملفّ اليمن الافتراضيّ (نسخة مستقلّة لكلّ مستدعٍ)."""
    reg = StandardsRegistry()
    for standard in (FAO29_WATER_QUALITY, HB60_SALINE_SODIC, AH210_LAND_CAPABILITY):
        reg.register(standard)
    reg.register_profile(YEMEN_DEFAULT_PROFILE)
    return reg


# ── كتالوج تدقيق المعايير (ملفٌّ مُصدَّر من تدقيق المالك 2026-11-24) ─────────────
#
# الكتالوج سجلُّ **هويّة وإصدار وحالة** لا بنودَ فنّيّة: يُسجَّل كلّ معيارٍ قابلٍ للتحليل
# كإصدارٍ في السجلّ (بلا بنود قابلة للتقييم)، وما ليس معياراً بإصدارٍ واحد (سياسة، تسعير،
# ادّعاء، مرجع سلسلة، رقمٌ غير متحقَّق) يبقى في الكتالوج بسببه — لا يُسقَط صامتاً.
#
# قاعدة الحالة **فشلٌ مغلق**: لا يصير الإصدار `active` إلّا بنصّ سريانٍ معروف + تحقّقٍ مؤكَّد +
# تاريخ نفاذٍ مسجَّل. كلّ ما عدا ذلك `unresolved` أو `draft` أو `withdrawn` — ولا يظهر أيٌّ منها
# التزاماً نافذاً (معيار القبول P0 في التدقيق نفسه).

CATALOG_DIR = Path(__file__).resolve().parent / "standards_catalog"
FARMLAND_AUDIT_CATALOG = CATALOG_DIR / "farmland_standards_audit_2026-11-24.json"
# بصمة ملفّ JSON نفسه (لا بصمة الـxlsx الأصليّ الذي ليس في المستودع): أيّ تعديلٍ على سجلٍّ
# أو تاريخٍ أو مصدر يُرفَض عند التحميل بدل أن يمرّ صامتاً. تحديث الكتالوج = ملفٌّ جديد + بصمة جديدة.
FARMLAND_AUDIT_CATALOG_SHA256 = "13c9a46454d6c1204f0e3a8ffac6f8a0b1aae95eb8ccf59451a0a1553427d6eb"

_EDITION_REF = re.compile(r"^(?P<id>[A-Z][A-Za-z0-9/ .]*?)\s*[-—–]\s*(?P<ver>(?:19|20)\d{2})$")
_ACTIVE_VALIDITY = frozenset(
    {
        "ساري",
        "ساري بحسب الناشر",
        "ساري بحسب فهرس CNIS",
        "معيار محلي ساري",
        "ساري؛ تجري مراجعة",
        # المرجع المدقَّق هو البديل الساري (الوارد في القائمة كان المُلغى):
        "الوارد ملغى؛ البديل ساري",
        "الإصدار المذكور ملغى؛ البديل ساري",
    }
)
_CONFIRMED = frozenset({"مؤكد", "مؤكد مع تحديث", "يحتاج تصحيح"})
_UNRESOLVED_VERIFICATION = frozenset({"غير محسوم", "تعارض سجلات", "إحالة مجملة"})
_PUBLISHED_NOT_YET_EFFECTIVE = "منشور؛ لم ينفذ بعد"


@dataclass(frozen=True)
class CatalogEntry:
    """مصير سجلٍّ واحد من الكتالوج: مُسجَّل كإصدار، أو باقٍ في الكتالوج بسببٍ مكتوب."""

    no: int
    verified_ref: str | None
    kind: str  # standard | policy | pricing | claim
    status: str | None  # حالة الإصدار في السجلّ إن سُجِّل
    reason: str
    standard_ref: str | None  # "id@version" إن سُجِّل

    @property
    def registered(self) -> bool:
        return self.standard_ref is not None


def _record_kind(rec: dict) -> str:
    validity = rec.get("validity_ar") or ""
    ref = rec.get("verified_ref") or ""
    if "تسعير" in validity:
        return "pricing"
    if any(w in validity for w in ("سياسة", "خطة", "وثيقة إدارية", "إرشاد", "محال إليه")):
        return "policy"
    if "ادعاء" in ref:
        return "claim"
    return "standard"


def _jurisdiction(standard_id: str) -> str:
    if standard_id.startswith("DB"):
        return "CN-local"
    if standard_id.startswith("T/"):
        return "CN-association"
    return "CN-national"


def _iso(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def audit_status(rec: dict) -> tuple[str, str]:
    """(حالة الإصدار، السبب) من سطر التدقيق — فشلٌ مغلق: المجهول ⇒ unresolved."""
    validity = rec.get("validity_ar") or ""
    verification = rec.get("verification_ar") or ""
    effective = rec.get("effective_from")
    if verification in _UNRESOLVED_VERIFICATION:
        return "unresolved", f"verification:{verification}"
    if "مسودة" in validity or "مسودة" in verification or "النشر النهائي غير مثبت" in validity:
        return "draft", f"validity:{validity}"
    if validity == "ملغى":
        return "withdrawn", "validity:ملغى"
    if validity == _PUBLISHED_NOT_YET_EFFECTIVE:
        if not effective:
            return "unresolved", "published_without_effective_date"
        return "active", "published_future_effective_date"
    if validity in _ACTIVE_VALIDITY and verification in _CONFIRMED:
        if not effective:
            return "unresolved", "effective_date_not_recorded"
        return "active", f"validity:{validity}"
    return "unresolved", f"validity_not_established:{validity or '-'}|{verification or '-'}"


def load_catalog(path: Path | None = None, expected_sha256: str | None = None) -> dict:
    """يحمّل كتالوجاً ويتحقّق من بصمته. الافتراضيّ: كتالوج التدقيق ببصمته المثبَّتة."""
    if path is None:
        path, expected_sha256 = (
            FARMLAND_AUDIT_CATALOG,
            expected_sha256 or FARMLAND_AUDIT_CATALOG_SHA256,
        )
    raw = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise StandardsRegistryError(f"catalog_hash_mismatch:{path.name}")
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc.get("records"), list) or not doc.get("version"):
        raise StandardsRegistryError("catalog_malformed")
    return doc


def register_catalog(registry: StandardsRegistry, doc: dict) -> list[CatalogEntry]:
    """يسجّل إصدارات الكتالوج القابلة للتحليل ويُرجِع مصير **كلّ** سجلّ (لا إسقاط صامت).

    إصداران للمعرّف نفسه بتاريخَي نفاذ ⇒ الأقدم يُغلَق عند نفاذ الأحدث (`effective_to`) ويُشار
    إلى خلَفه (`superseded_by`) — فيبقى الأقدم الساريَ حتّى ذلك التاريخ لا قبله ولا بعده.
    """
    catalog_ref = f"{doc.get('catalog_id', 'catalog')}@{doc['version']}"
    entries: list[CatalogEntry] = []
    staged: list[Standard] = []
    seen: set[tuple[str, str]] = set()
    for rec in doc["records"]:
        no = int(rec["no"])
        ref = rec.get("verified_ref")
        kind = _record_kind(rec)
        if kind != "standard":
            entries.append(CatalogEntry(no, ref, kind, None, f"not_a_standard:{kind}", None))
            continue
        m = _EDITION_REF.match((ref or "").strip())
        if not m:
            entries.append(CatalogEntry(no, ref, kind, None, "ref_not_a_single_edition", None))
            continue
        sid, version = " ".join(m.group("id").split()), m.group("ver")
        if (sid, version) in seen:
            entries.append(CatalogEntry(no, ref, kind, None, "duplicate_edition", None))
            continue
        seen.add((sid, version))
        status, reason = audit_status(rec)
        effective_from = _iso(rec.get("effective_from"))
        withdrawn_on = _iso(rec.get("withdrawn_on"))
        effective_to = (
            withdrawn_on
            if status == "withdrawn"
            and withdrawn_on
            and (not effective_from or withdrawn_on > effective_from)
            else None
        )
        staged.append(
            Standard(
                standard_id=sid,
                version=version,
                title=rec.get("subject_ar") or sid,
                issuer=sid.split(" ", 1)[0],
                effective_from=effective_from,
                status=status,
                clauses=(),
                effective_to=effective_to,
                kind="standard",
                jurisdiction=_jurisdiction(sid),
                sources=tuple(rec.get("sources") or ()),
                audit={
                    "catalog": catalog_ref,
                    "no": no,
                    "status_reason": reason,
                    "received_ref": rec.get("received_ref"),
                    "verification_ar": rec.get("verification_ar"),
                    "validity_ar": rec.get("validity_ar"),
                    "issued_on": rec.get("issued_on"),
                    "withdrawn_on": rec.get("withdrawn_on"),
                    "correction_note_ar": rec.get("correction_note_ar"),
                    "title_zh": rec.get("title_zh"),
                    "verified_on": rec.get("verified_on"),
                },
            )
        )
        entries.append(CatalogEntry(no, ref, kind, status, reason, f"{sid}@{version}"))

    # الاستبدال المجدول داخل المعرّف نفسه (مثلاً GB/T 33469-2016 ← 2026 النافذ 2027-05-01).
    by_id: dict[str, list[Standard]] = {}
    for s in staged:
        if s.status == "active" and s.effective_from is not None:
            by_id.setdefault(s.standard_id, []).append(s)
    successor: dict[str, Standard] = {}
    for versions in by_id.values():
        versions.sort(key=lambda s: s.effective_from)
        for older, newer in zip(versions, versions[1:], strict=False):
            successor[older.ref] = newer
    for s in staged:
        nxt = successor.get(s.ref)
        if nxt is not None and s.effective_to is None:
            s = replace(s, effective_to=nxt.effective_from, superseded_by=nxt.ref)
        registry.register(s)
    return entries


def catalog_registry(path: Path | None = None) -> tuple[StandardsRegistry, list[CatalogEntry]]:
    """السجلّ الافتراضيّ + كتالوج التدقيق. لا اعتماد محلّيّ لأيّ معيار كتالوج (reference_only)."""
    reg = default_registry()
    entries = register_catalog(reg, load_catalog(path))
    return reg, entries

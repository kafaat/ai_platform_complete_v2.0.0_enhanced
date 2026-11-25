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
- **ملفّات الاعتماد (profiles)** حسب الدولة/المنطقة/المشروع تختار المعايير وإصداراتها،
  وتسمح **بالتشديد فقط**: تجاوزٌ يُرخي حدّاً (يرفع حدّاً أعلى أو يخفض حدّاً أدنى) يُرفَض
  عند البناء — مشروعٌ لا يستطيع أن «يُطابق» بتليين المعيار.

المعادلات والمطابقة نفسها في `compliance_engine.py`؛ هذا الملفّ بيانات وحلّ إصدارات فقط.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date

REGISTRY_VERSION = "farmland-standards.v1"

_STATUSES = ("active", "superseded", "withdrawn")
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
    effective_from: date
    status: str
    clauses: tuple[Clause, ...]
    superseded_by: str | None = None  # "standard_id@version"
    effective_to: date | None = None

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
class ComplianceProfile:
    profile_id: str
    country: str
    standards: tuple[str, ...]  # "standard_id" (الساري) أو "standard_id@version" (مُثبَّت)
    region: str | None = None
    project: str | None = None
    overrides: tuple[ClauseOverride, ...] = ()
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
        self.profiles[profile.profile_id] = profile

    # ── الحلّ ───────────────────────────────────────────────────────────
    def versions(self, standard_id: str) -> list[Standard]:
        out = [s for (sid, _), s in self.standards.items() if sid == standard_id]
        if not out:
            raise StandardsRegistryError(f"unknown_standard:{standard_id}")
        return sorted(out, key=lambda s: s.effective_from)

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

        الساري = حالته ليست withdrawn، وبدأ سريانه في `on` أو قبله، ولم ينتهِ قبله؛ وعند تعدّد
        المرشّحين يفوز الأحدث سرياناً. لا مرشّح ⇒ خطأ صريح لا ارتداد إلى أقدم إصدار.
        """
        on = on or date.today()
        candidates = [
            s
            for s in self.versions(standard_id)
            if s.status != "withdrawn"
            and s.effective_from <= on
            and (s.effective_to is None or on < s.effective_to)
        ]
        if not candidates:
            raise StandardsRegistryError(f"no_effective_version:{standard_id}@{on.isoformat()}")
        return max(candidates, key=lambda s: s.effective_from)

    def resolve(self, ref: str, on: date | None = None) -> Standard:
        """«id» ⇒ الساري؛ «id@version» ⇒ ذلك الإصدار (المسحوب يُرفَض حتى لو مُثبَّتاً)."""
        if "@" in ref:
            sid, version = ref.split("@", 1)
            standard = self.get(sid, version)
            if standard.status == "withdrawn":
                raise StandardsRegistryError(f"withdrawn_standard:{standard.ref}")
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
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


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
    if s.effective_to is not None and s.effective_to <= s.effective_from:
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
_AH210 = (
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

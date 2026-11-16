"""One pest/disease code registry (W1-19, finding scout-3).

Before this module three vocabularies described the same organisms and did not meet:

* the symptom rules of ``services/sahool-platform/api/disease_diagnosis.py`` emit
  crop-scoped codes (``wheat.rust``, ``wheat.aphid``, ``coffee.leaf_rust``);
* the IPM advisor (``api/ipm_advisor.py``) keyed its plans by ``fall_armyworm`` /
  ``wheat_rust`` / ``aphid`` plus a few Arabic names;
* the edge detector (``services/edge-inference/models/pest_detector.py``) labels model
  classes ``armyworm``, ``rust``, ``blight``, ``coffee_borer`` ...

so a diagnosis never became an IPM plan (``ipm_plan("wheat.rust")`` was unsupported).

Here every organism or disorder has ONE canonical code. Every other spelling (crop-scoped
diagnosis/scouting codes, edge model labels, Arabic names) is an alias that resolves to it.
The registry also says, per code, whether an IPM plan applies: pests and diseases have one;
nutrient, water and salinity disorders do not and carry a named referral instead, so a
caller never gets an IPM ladder for a nitrogen deficiency and never a silent ``None``.

Pure data and lookups. No product names and no doses: plans and safety live with their
owners (the IPM advisor and the chemical-safety gate).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Categories for which an IPM ladder is the right answer.
IPM_CATEGORIES = frozenset({"pest", "disease"})

#: Where a non-IPM category is referred instead.
NON_IPM_REFERRAL = {
    "nutrient": "soil_or_tissue_lab_test",
    "water_stress": "irrigation_review",
    "abiotic": "soil_salinity_review",
}

#: Public path that serves a plan for a canonical code.
IPM_PLAN_PATH = "/api/v1/ipm/plan"


@dataclass(frozen=True)
class TaxonEntry:
    code: str
    category: str  # pest | disease | nutrient | water_stress | abiotic
    name_ar: str
    scientific: str | None
    aliases: tuple[str, ...] = ()
    referral: str | None = None  # overrides the category referral for a non-IPM entry

    @property
    def ipm_applicable(self) -> bool:
        return self.category in IPM_CATEGORIES


_ENTRIES: tuple[TaxonEntry, ...] = (
    # ── pests ────────────────────────────────────────────────────────────
    TaxonEntry(
        "aphid",
        "pest",
        "المنّ",
        "Aphidoidea",
        aliases=(
            "wheat.aphid",
            "barley.aphid",
            "alfalfa.aphid",
            "منّ",
            "المن",
            "المنّ",
        ),
    ),
    TaxonEntry(
        "fall_armyworm",
        "pest",
        "دودة الحشد الخريفيّة",
        "Spodoptera frugiperda",
        aliases=(
            "armyworm",
            "دودة الحشد",
            "دودة الحشد الخريفية",
            "الحشد",
        ),
    ),
    TaxonEntry(
        "stem_borer",
        "pest",
        "حفّار ساق الذرة",
        "Sesamia spp. / Chilo partellus",
        aliases=("حفار الساق", "حفّار الساق"),
    ),
    TaxonEntry(
        "tomato_leafminer",
        "pest",
        "حفّار أوراق الطماطم (توتا)",
        "Tuta absoluta",
        aliases=("leaf_miner", "tomato.tuta", "حفار الأوراق", "توتا"),
    ),
    TaxonEntry(
        "spider_mite",
        "pest",
        "العنكبوت الأحمر",
        "Tetranychus urticae",
        aliases=("red_spider_mite", "عنكبوت أحمر", "العنكبوت الأحمر"),
    ),
    TaxonEntry(
        "coffee_berry_borer",
        "pest",
        "ثاقبة ثمار البنّ",
        "Hypothenemus hampei",
        aliases=("coffee_borer", "coffee.berry_borer", "حفار القهوة", "ثاقبة ثمار البن"),
    ),
    # ── diseases ─────────────────────────────────────────────────────────
    TaxonEntry(
        "wheat_rust",
        "disease",
        "صدأ القمح",
        "Puccinia spp.",
        aliases=("rust", "wheat.rust", "صدأ القمح", "صدأ"),
    ),
    TaxonEntry(
        "coffee_leaf_rust",
        "disease",
        "صدأ أوراق البنّ",
        "Hemileia vastatrix",
        aliases=("coffee_rust", "coffee.leaf_rust", "صدأ القهوة", "صدأ أوراق البن"),
    ),
    TaxonEntry(
        "late_blight",
        "disease",
        "اللفحة المتأخّرة",
        "Phytophthora infestans",
        aliases=("blight", "tomato.late_blight", "potato.late_blight", "لفحة"),
    ),
    TaxonEntry(
        "bacterial_wilt",
        "disease",
        "الذبول البكتيري",
        "Ralstonia solanacearum",
        aliases=("ذبول بكتيري",),
    ),
    # ── non-IPM disorders that the symptom rules also emit ───────────────
    TaxonEntry(
        "n_deficiency",
        "nutrient",
        "نقص نيتروجين",
        None,
        aliases=("wheat.n_deficiency", "barley.n_deficiency"),
    ),
    TaxonEntry(
        "fe_deficiency",
        "nutrient",
        "نقص حديد",
        None,
        aliases=("wheat.fe_deficiency", "citrus.fe_deficiency"),
    ),
    TaxonEntry(
        "zn_deficiency",
        "nutrient",
        "نقص زنك",
        None,
        aliases=("coffee.zn_deficiency",),
    ),
    TaxonEntry(
        "water_stress",
        "water_stress",
        "إجهاد مائي",
        None,
        aliases=("qat.water_stress",),
    ),
    TaxonEntry(
        "salinity_stress",
        "water_stress",  # the category the symptom rule emits
        "إجهاد ملوحة",
        None,
        aliases=("generic.salinity",),
        referral="soil_salinity_review",
    ),
)


def _norm(value: str) -> str:
    return value.strip().casefold()


def _build_index() -> dict[str, TaxonEntry]:
    index: dict[str, TaxonEntry] = {}
    for entry in _ENTRIES:
        for spelling in (entry.code, *entry.aliases):
            key = _norm(spelling)
            other = index.get(key)
            if other is not None and other.code != entry.code:
                raise ValueError(f"pest taxonomy alias {spelling!r} maps to two codes")
            index[key] = entry
    return index


_BY_CODE: dict[str, TaxonEntry] = {e.code: e for e in _ENTRIES}
_INDEX: dict[str, TaxonEntry] = _build_index()


def entries() -> tuple[TaxonEntry, ...]:
    return _ENTRIES


def codes() -> tuple[str, ...]:
    return tuple(e.code for e in _ENTRIES)


def get(code: str) -> TaxonEntry | None:
    """Exact canonical lookup (no alias)."""
    return _BY_CODE.get(code)


def resolve(value: str | None) -> TaxonEntry | None:
    """Any known spelling (canonical, crop-scoped code, edge label, Arabic) -> entry."""
    if not isinstance(value, str) or not value.strip():
        return None
    return _INDEX.get(_norm(value))


def resolve_code(value: str | None) -> str | None:
    entry = resolve(value)
    return entry.code if entry is not None else None


def ipm_plan_ref(value: str | None) -> dict | None:
    """The IPM plan a code points to, or ``None`` when no plan applies or the code is unknown."""
    entry = resolve(value)
    if entry is None or not entry.ipm_applicable:
        return None
    return {"code": entry.code, "path": f"{IPM_PLAN_PATH}?pest={entry.code}"}


def ipm_resolution(value: str | None) -> dict:
    """What a caller should do with a code: an IPM plan, a named referral, or unresolved.

    Never silently empty: an unknown code says ``code_not_in_taxonomy``.
    """
    entry = resolve(value)
    if entry is None:
        return {"taxonomy_code": None, "ipm_plan_ref": None, "ipm_status": "code_not_in_taxonomy"}
    if entry.ipm_applicable:
        return {
            "taxonomy_code": entry.code,
            "ipm_plan_ref": ipm_plan_ref(entry.code),
            "ipm_status": "plan_available",
        }
    return {
        "taxonomy_code": entry.code,
        "ipm_plan_ref": None,
        "ipm_status": "not_applicable",
        "referral": entry.referral or NON_IPM_REFERRAL[entry.category],
    }

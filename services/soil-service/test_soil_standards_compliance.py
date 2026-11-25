"""Farmland Phase 2 · 0001 — standards registry + compliance engine contract."""

import hashlib
import shutil
from dataclasses import replace
from datetime import date, datetime

import pytest
from compliance_engine import Observation, classify_band, evaluate_profile, evaluate_standards
from standards_registry import (
    FAO29_WATER_QUALITY,
    FARMLAND_AUDIT_CATALOG,
    FARMLAND_AUDIT_CATALOG_SHA256,
    HB60_SALINE_SODIC,
    Band,
    Clause,
    ClauseOverride,
    ComplianceProfile,
    Standard,
    StandardAdoption,
    StandardsRegistry,
    StandardsRegistryError,
    audit_status,
    catalog_registry,
    default_registry,
    load_catalog,
    register_catalog,
)

pytestmark = pytest.mark.unit

ON = date(2026, 11, 25)
FRESH = date(2026, 10, 1)


def _obs(parameter, value, unit, observed_on=FRESH):
    return Observation(parameter, value, unit, source="lab:test", observed_on=observed_on)


def _std(version, effective_from, status="active", superseded_by=None, upper=4.0, **kw):
    return Standard(
        standard_id="TEST-STD",
        version=version,
        title="test",
        issuer="test",
        effective_from=effective_from,
        status=status,
        superseded_by=superseded_by,
        clauses=(
            Clause(
                clause_id="ece",
                parameter="ece_ds_m",
                unit="dS/m",
                limit_kind="max",
                title_ar="t",
                source="test source",
                upper=upper,
            ),
        ),
        **kw,
    )


# ── السجلّ: الإصدارات والاستبدال ───────────────────────────────────────────


def test_default_registry_resolves_every_seeded_standard_and_the_yemen_profile():
    reg = default_registry()
    refs = [s.ref for s in reg.profile_standards("YE-default", ON)]
    assert refs == ["FAO-29@rev1-1985", "USDA-HB60@1954", "USDA-AH210-INDICATIVE@v1"]


def test_every_seeded_clause_names_its_source_and_is_not_claimed_regionally_calibrated():
    reg = default_registry()
    for standard in reg.profile_standards("YE-default", ON):
        for clause in standard.clauses:
            assert clause.source.strip(), clause.clause_id
            assert clause.calibrated_for_region is False, clause.clause_id


def test_current_picks_the_version_in_force_on_the_date_and_keeps_history_queryable():
    reg = StandardsRegistry()
    reg.register(_std("v1", date(2000, 1, 1), status="superseded", superseded_by="TEST-STD@v2"))
    reg.register(_std("v2", date(2020, 1, 1), upper=3.0))
    assert reg.current("TEST-STD", date(2010, 6, 1)).version == "v1"
    assert reg.current("TEST-STD", date(2021, 6, 1)).version == "v2"
    # superseded stays queryable by explicit pin (historical audit)
    assert reg.resolve("TEST-STD@v1").clause("ece").upper == 4.0
    assert reg.supersession_chain("TEST-STD", "v1") == ["TEST-STD@v1", "TEST-STD@v2"]


def test_no_version_in_force_is_an_error_not_a_fallback_to_the_oldest():
    reg = StandardsRegistry()
    reg.register(_std("v1", date(2030, 1, 1)))
    with pytest.raises(StandardsRegistryError, match="no_effective_version"):
        reg.current("TEST-STD", ON)


def test_withdrawn_versions_are_never_current_and_cannot_be_pinned():
    reg = StandardsRegistry()
    reg.register(_std("v1", date(2000, 1, 1), status="withdrawn"))
    with pytest.raises(StandardsRegistryError, match="no_effective_version"):
        reg.current("TEST-STD", ON)
    with pytest.raises(StandardsRegistryError, match="withdrawn_standard"):
        reg.resolve("TEST-STD@v1")


def test_effective_to_closes_a_version_window():
    reg = StandardsRegistry()
    reg.register(_std("v1", date(2000, 1, 1), effective_to=date(2010, 1, 1)))
    assert reg.current("TEST-STD", date(2009, 12, 31)).version == "v1"
    with pytest.raises(StandardsRegistryError, match="no_effective_version"):
        reg.current("TEST-STD", date(2010, 1, 1))


@pytest.mark.parametrize(
    "bad",
    [
        _std("v1", date(2000, 1, 1), status="superseded"),  # no successor
        _std("v1", date(2000, 1, 1), status="proposed"),
        _std("v1", date(2000, 1, 1), effective_to=date(1999, 1, 1)),
    ],
)
def test_structurally_invalid_standards_are_rejected_at_registration(bad):
    with pytest.raises(StandardsRegistryError):
        StandardsRegistry().register(bad)


def test_duplicate_version_and_supersession_cycle_are_rejected():
    reg = StandardsRegistry()
    reg.register(_std("v1", date(2000, 1, 1), status="superseded", superseded_by="TEST-STD@v2"))
    with pytest.raises(StandardsRegistryError, match="duplicate_standard_version"):
        reg.register(_std("v1", date(2000, 1, 1)))
    reg.register(_std("v2", date(2010, 1, 1), status="superseded", superseded_by="TEST-STD@v1"))
    with pytest.raises(StandardsRegistryError, match="supersession_cycle"):
        reg.supersession_chain("TEST-STD", "v1")


@pytest.mark.parametrize(
    "clause",
    [
        Clause("c", "p", "u", "max", "t", source=""),  # no source
        Clause("c", "p", "u", "max", "t", source="s"),  # max without upper
        Clause("c", "p", "u", "range", "t", source="s", lower=5, upper=1),
        Clause(
            "c",
            "p",
            "u",
            "bands",
            "t",
            source="s",
            bands=(Band("a", 0, 1), Band("b", 2, None)),
            pass_labels=("a",),
        ),
        Clause(
            "c",
            "p",
            "u",
            "bands",
            "t",
            source="s",
            bands=(Band("a", 0, None), Band("b", 1, 2)),
            pass_labels=("a",),
        ),
        Clause(
            "c", "p", "u", "bands", "t", source="s", bands=(Band("a", 0, 1),), pass_labels=("zzz",)
        ),
        Clause("c", "p", "u", "max", "t", source="s", upper=float("nan")),
    ],
)
def test_invalid_clauses_are_rejected(clause):
    std = replace(_std("v1", date(2000, 1, 1)), clauses=(clause,))
    with pytest.raises(StandardsRegistryError):
        StandardsRegistry().register(std)


# ── ملفّات الاعتماد: تشديد فقط ───────────────────────────────────────────


def _profile(*overrides):
    return ComplianceProfile("P1", "YE", ("USDA-HB60",), project="farm-180ha", overrides=overrides)


def test_profile_override_may_tighten_and_the_tightened_limit_is_what_is_evaluated():
    reg = default_registry()
    reg.register_profile(
        _profile(ClauseOverride("USDA-HB60", "saline.ECe", "pivot crop is sensitive", upper=2.0))
    )
    (hb60,) = reg.profile_standards("P1", ON)
    assert hb60.clause("saline.ECe").upper == 2.0
    assert "tightened by profile P1" in hb60.clause("saline.ECe").source
    report = evaluate_profile(
        reg, "P1", [_obs("ece_ds_m", 3.0, "dS/m"), _obs("esp_pct", 5.0, "%")], on=ON
    )
    assert report.verdict == "non_compliant"  # 3.0 passes HB60 (<4) but fails the tightened 2.0


@pytest.mark.parametrize(
    "override, match",
    [
        (ClauseOverride("USDA-HB60", "saline.ECe", "looser", upper=6.0), "override_loosens_upper"),
        (ClauseOverride("USDA-HB60", "saline.ECe", "", upper=2.0), "override_without_reason"),
        (ClauseOverride("USDA-HB60", "saline.ECe", "noop"), "override_changes_nothing"),
        (
            ClauseOverride("USDA-HB60", "saline.ECe", "lower on max", lower=1.0),
            "override_loosens_lower",
        ),
        (
            ClauseOverride("FAO-29", "T1.pH", "not in profile", lower=7.0),
            "override_targets_unlisted_standard",
        ),
    ],
)
def test_profile_overrides_that_loosen_or_are_unjustified_are_refused(override, match):
    reg = default_registry()
    with pytest.raises(StandardsRegistryError, match=match):
        reg.register_profile(_profile(override))


def test_range_override_cannot_widen_and_cannot_invert():
    reg = default_registry()
    with pytest.raises(StandardsRegistryError, match="override_loosens_lower"):
        reg.register_profile(
            ComplianceProfile(
                "P2",
                "YE",
                ("FAO-29",),
                overrides=(ClauseOverride("FAO-29", "T1.pH", "wider", lower=6.0),),
            )
        )
    with pytest.raises(StandardsRegistryError, match="override_inverts_range"):
        reg.register_profile(
            ComplianceProfile(
                "P3",
                "YE",
                ("FAO-29",),
                overrides=(ClauseOverride("FAO-29", "T1.pH", "inverted", lower=8.0, upper=7.0),),
            )
        )
    reg.register_profile(
        ComplianceProfile(
            "P4",
            "YE",
            ("FAO-29",),
            overrides=(ClauseOverride("FAO-29", "T1.pH", "narrower", lower=7.0),),
        )
    )
    (fao,) = reg.profile_standards("P4", ON)
    assert (fao.clause("T1.pH").lower, fao.clause("T1.pH").upper) == (7.0, 8.4)


# ── محرّك المطابقة ────────────────────────────────────────────────────────


def test_bands_are_half_open_at_the_published_boundaries():
    ecw = FAO29_WATER_QUALITY.clause("T1.salinity.ECw")
    assert classify_band(ecw, 0.69) == "none"
    assert classify_band(ecw, 0.7) == "slight_to_moderate"
    assert classify_band(ecw, 3.0) == "severe"
    assert classify_band(ecw, -0.1) is None
    assert classify_band(ecw, float("nan")) is None


def test_full_water_panel_passes_only_when_every_applicable_clause_passes():
    obs = [
        _obs("ecw_ds_m", 0.5, "dS/m"),
        _obs("b_mg_l", 0.3, "mg/L"),
        _obs("ph", 7.4, "pH"),
    ]
    report = evaluate_standards([FAO29_WATER_QUALITY], obs, on=ON)
    # SAR/chloride clauses are surface-irrigation specific and were not requested
    assert report.verdict == "compliant"
    assert report.counts == {"pass": 3, "fail": 0, "not_evaluated": 0, "not_applicable": 2}


def test_requesting_the_surface_irrigation_context_makes_missing_sar_block_compliance():
    obs = [_obs("ecw_ds_m", 0.5, "dS/m"), _obs("b_mg_l", 0.3, "mg/L"), _obs("ph", 7.4, "pH")]
    report = evaluate_standards([FAO29_WATER_QUALITY], obs, on=ON, contexts={"surface_irrigation"})
    assert report.verdict == "incomplete"
    missing = {r.clause_id for r in report.results if r.reason == "missing_observation"}
    assert missing == {"T1.sodium.SAR.surface", "T1.chloride.surface"}


def test_a_single_failure_dominates_missing_data():
    report = evaluate_standards([FAO29_WATER_QUALITY], [_obs("ecw_ds_m", 3.5, "dS/m")], on=ON)
    assert report.verdict == "non_compliant"
    ecw = next(r for r in report.results if r.clause_id == "T1.salinity.ECw")
    assert ecw.status == "fail" and ecw.band == "severe"
    assert ecw.evidence["observed"]["value"] == 3.5
    assert ecw.evidence["limit"]["source"].startswith("FAO Irrigation and Drainage Paper 29")


def test_no_observations_is_incomplete_never_compliant():
    assert evaluate_standards([HB60_SALINE_SODIC], [], on=ON).verdict == "incomplete"


@pytest.mark.parametrize(
    "obs, reason",
    [
        (_obs("ece_ds_m", 3.0, "mS/cm"), "unit_mismatch"),
        (_obs("ece_ds_m", float("nan"), "dS/m"), "non_finite_value"),
        (_obs("ece_ds_m", float("inf"), "dS/m"), "non_finite_value"),
        (_obs("ece_ds_m", 3.0, "dS/m", observed_on=None), "observation_date_missing"),
        (_obs("ece_ds_m", 3.0, "dS/m", observed_on=date(2020, 1, 1)), "observation_stale"),
        (_obs("ece_ds_m", 3.0, "dS/m", observed_on=date(2027, 1, 1)), "observation_in_future"),
    ],
)
def test_untrustworthy_observations_are_not_evaluated_rather_than_passed(obs, reason):
    report = evaluate_standards([HB60_SALINE_SODIC], [obs, _obs("esp_pct", 5.0, "%")], on=ON)
    ece = next(r for r in report.results if r.clause_id == "saline.ECe")
    assert (ece.status, ece.reason) == ("not_evaluated", reason)
    assert report.verdict == "incomplete"


@pytest.mark.parametrize(
    "ece, esp, verdict",
    [
        (3.99, 14.99, "compliant"),
        (4.0, 5.0, "non_compliant"),  # HB60: saline at ECe >= 4 — the threshold itself fails
        (1.0, 15.0, "non_compliant"),  # HB60: sodic at ESP >= 15
    ],
)
def test_hb60_class_thresholds_are_exclusive_upper_bounds(ece, esp, verdict):
    obs = [_obs("ece_ds_m", ece, "dS/m"), _obs("esp_pct", esp, "%")]
    assert evaluate_standards([HB60_SALINE_SODIC], obs, on=ON).verdict == verdict


def test_inclusive_upper_bound_still_passes_on_the_limit():
    std = _std("v1", date(2000, 1, 1), upper=4.0)
    assert evaluate_standards([std], [_obs("ece_ds_m", 4.0, "dS/m")], on=ON).verdict == "compliant"


def test_duplicate_observation_for_one_parameter_is_an_error():
    with pytest.raises(ValueError, match="duplicate_observation"):
        evaluate_standards(
            [HB60_SALINE_SODIC], [_obs("esp_pct", 1, "%"), _obs("esp_pct", 2, "%")], on=ON
        )


def test_report_serialises_with_evidence_for_audit():
    report = evaluate_profile(
        default_registry(), "YE-default", [_obs("ece_ds_m", 1.0, "dS/m")], on=ON
    )
    out = report.to_dict()
    assert out["profile_id"] == "YE-default" and out["verdict"] == "incomplete"
    assert out["evaluated_on"] == "2026-11-25"
    assert all(
        {"standard", "clause", "status", "reason", "evidence"} <= set(r) for r in out["results"]
    )


# ── الصلاحية ≠ الاعتماد المحلّيّ ──────────────────────────────────────────


def test_literature_compliance_is_technical_not_legally_binding_by_default():
    obs = [_obs("ece_ds_m", 1.0, "dS/m"), _obs("esp_pct", 5.0, "%")]
    reg = default_registry()
    reg.register_profile(ComplianceProfile("P-tech", "YE", ("USDA-HB60",)))
    report = evaluate_profile(reg, "P-tech", obs, on=ON)
    assert report.verdict == "compliant"
    assert report.legally_binding is False
    hb60 = report.to_dict()["standards"]["USDA-HB60@1954"]
    assert (hb60["validity"], hb60["adoption"]) == ("active", "reference_only")


def test_adopted_standard_with_authority_and_reference_makes_the_verdict_binding():
    reg = default_registry()
    adoption = StandardAdoption(
        "USDA-HB60",
        "adopted",
        authority="MAI Yemen",
        reference="decree 12/2026",
        adopted_on=date(2026, 1, 1),
    )
    reg.register_profile(ComplianceProfile("P-adopt", "YE", ("USDA-HB60",), adoption=(adoption,)))
    obs = [_obs("ece_ds_m", 1.0, "dS/m"), _obs("esp_pct", 5.0, "%")]
    report = evaluate_profile(reg, "P-adopt", obs, on=ON)
    assert report.legally_binding is True
    std = report.to_dict()["standards"]["USDA-HB60@1954"]
    assert (
        std["adoption_authority"] == "MAI Yemen" and std["adoption_reference"] == "decree 12/2026"
    )


def test_binding_requires_every_evaluated_standard_to_be_adopted():
    reg = default_registry()
    adoption = StandardAdoption("USDA-HB60", "adopted", authority="MAI", reference="d1")
    reg.register_profile(
        ComplianceProfile("P-mix", "YE", ("USDA-HB60", "FAO-29"), adoption=(adoption,))
    )
    obs = [_obs("ece_ds_m", 1.0, "dS/m"), _obs("esp_pct", 5.0, "%"), _obs("ph", 7.0, "pH")]
    assert evaluate_profile(reg, "P-mix", obs, on=ON).legally_binding is False


@pytest.mark.parametrize(
    "adoption, match",
    [
        (StandardAdoption("USDA-HB60", "adopted"), "adoption_without_authority_or_reference"),
        (
            StandardAdoption("USDA-HB60", "provisional", authority="MAI"),
            "adoption_without_authority_or_reference",
        ),
        (
            StandardAdoption("USDA-HB60", "ratified", authority="a", reference="r"),
            "unknown_adoption_status",
        ),
        (
            StandardAdoption("FAO-29", "adopted", authority="a", reference="r"),
            "adoption_targets_unlisted_standard",
        ),
    ],
)
def test_adoption_claims_without_source_or_scope_are_refused(adoption, match):
    with pytest.raises(StandardsRegistryError, match=match):
        default_registry().register_profile(
            ComplianceProfile("P-bad", "YE", ("USDA-HB60",), adoption=(adoption,))
        )


def test_yemen_default_profile_claims_no_local_adoption():
    reg = default_registry()
    for sid in ("FAO-29", "USDA-HB60", "USDA-AH210-INDICATIVE"):
        assert reg.adoption_status("YE-default", sid).status == "reference_only"


# ── كتالوج تدقيق المعايير (2026-11-24) ────────────────────────────────────


def _catalog():
    return catalog_registry()


def test_every_audit_record_has_a_fate_and_none_is_dropped_silently():
    doc = load_catalog()
    reg, entries = _catalog()
    assert len(doc["records"]) == len(entries) == 158
    assert sorted(e.no for e in entries) == list(range(1, 159))
    for e in entries:
        assert e.reason, e
        if e.registered:
            assert reg.get(*e.standard_ref.split("@", 1)).audit["no"] == e.no


def test_catalog_provenance_is_pinned_to_the_audit_file():
    doc = load_catalog()
    assert doc["version"] == "2026-11-24"
    assert len(doc["source_sha256"]) == 64
    assert FARMLAND_AUDIT_CATALOG.name == "farmland_standards_audit_2026-11-24.json"


def test_scheduled_supersession_keeps_the_old_edition_in_force_until_the_new_one_starts():
    reg, _ = _catalog()
    assert reg.current("GB/T 33469", date(2026, 11, 25)).version == "2016"
    assert reg.current("GB/T 33469", date(2027, 4, 30)).version == "2016"
    assert reg.current("GB/T 33469", date(2027, 5, 1)).version == "2026"
    assert reg.supersession_chain("GB/T 33469", "2016") == ["GB/T 33469@2016", "GB/T 33469@2026"]


def test_a_published_future_edition_is_never_an_obligation_before_it_takes_effect():
    reg, _ = _catalog()
    with pytest.raises(StandardsRegistryError, match="no_effective_version"):
        reg.current("GB/T 48026", date(2026, 11, 25))
    with pytest.raises(StandardsRegistryError, match="not_yet_effective"):
        reg.resolve("GB/T 48026@2026", date(2026, 11, 25))
    assert reg.resolve("GB/T 48026@2026", date(2027, 2, 1)).version == "2026"


def test_withdrawn_editions_close_on_their_recorded_withdrawal_date_and_cannot_be_pinned():
    reg, _ = _catalog()
    db = reg.get("DB3402/T 78", "2024")
    assert db.status == "withdrawn" and db.effective_to == date(2026, 8, 3)
    with pytest.raises(StandardsRegistryError, match="no_effective_version"):
        reg.current(
            "DB3402/T 78", date(2026, 1, 1)
        )  # withdrawn is never current, even inside its old window
    with pytest.raises(StandardsRegistryError, match="withdrawn_standard"):
        reg.resolve("DB3402/T 78@2024")


def test_unresolved_validity_is_never_presented_as_in_force():
    reg, entries = _catalog()
    unresolved = [e for e in entries if e.status == "unresolved"]
    assert unresolved
    for e in unresolved:
        sid, ver = e.standard_ref.split("@", 1)
        with pytest.raises(StandardsRegistryError):
            reg.resolve(e.standard_ref)
        with pytest.raises(StandardsRegistryError):
            reg.current(sid, date(2026, 11, 25))
    # confirmed and in force but no effective date recorded ⇒ not computable on a date
    assert reg.get("GB/T 50363", "2018").audit["status_reason"] == "effective_date_not_recorded"


def test_corrected_references_are_registered_under_the_verified_identity():
    reg, _ = _catalog()
    gb18877 = reg.get("GB/T 18877", "2020")  # received as "GB 18877-2020"; /T changes its identity
    assert gb18877.audit["received_ref"] != "GB/T 18877-2020"
    assert reg.get("GB 50194", "2014").audit["verification_ar"] == "يحتاج تصحيح"
    with pytest.raises(StandardsRegistryError):
        reg.get("GB 50194", "2022")


def test_policies_pricing_claims_and_series_refs_stay_catalogue_only():
    _, entries = _catalog()
    kinds = {e.kind for e in entries if not e.registered}
    assert {"policy", "pricing", "claim"} <= kinds
    assert all(e.standard_ref is None for e in entries if e.kind != "standard")
    series = next(e for e in entries if e.no == 18)  # NY/T 1121 as a whole series
    assert series.reason == "ref_not_a_single_edition"


def test_catalogue_standards_are_reference_only_and_carry_jurisdiction_and_sources():
    reg, entries = _catalog()
    reg.register_profile(ComplianceProfile("P-cn", "YE", ("GB/T 30600",)))
    assert reg.adoption_status("P-cn", "GB/T 30600").status == "reference_only"
    gb = reg.get("GB/T 30600", "2022")
    assert gb.jurisdiction == "CN-national" and gb.sources and gb.clauses == ()
    assert reg.get("DB36/T 2180.1", "2025").jurisdiction == "CN-local"
    assert reg.get("T/CECS 1043", "2022").jurisdiction == "CN-association"


@pytest.mark.parametrize(
    "rec, expected",
    [
        (
            {"validity_ar": "ساري", "verification_ar": "مؤكد", "effective_from": "2020-01-01"},
            "active",
        ),
        (
            {"validity_ar": "ساري", "verification_ar": "تحقق جزئي", "effective_from": "2020-01-01"},
            "unresolved",
        ),
        ({"validity_ar": "ساري", "verification_ar": "مؤكد", "effective_from": None}, "unresolved"),
        (
            {"validity_ar": "ساري", "verification_ar": "غير محسوم", "effective_from": "2020-01-01"},
            "unresolved",
        ),
        ({"validity_ar": "مسودة؛ الإصدار النهائي غير مثبت", "verification_ar": "مؤكد"}, "draft"),
        ({"validity_ar": "ملغى", "verification_ar": "مؤكد"}, "withdrawn"),
        (
            {
                "validity_ar": "نصّ جديد لم يُعرَف",
                "verification_ar": "مؤكد",
                "effective_from": "2020-01-01",
            },
            "unresolved",
        ),
    ],
)
def test_audit_status_mapping_fails_closed(rec, expected):
    assert audit_status(rec)[0] == expected


def test_draft_editions_are_never_current_or_pinnable():
    reg = StandardsRegistry()
    doc = {
        "catalog_id": "t",
        "version": "1",
        "records": [
            {
                "no": 1,
                "verified_ref": "NY/T 9999-2025",
                "validity_ar": "مسودة؛ الإصدار النهائي غير مثبت",
                "verification_ar": "مسودة مثبتة؛ النهائي غير محسوم",
                "effective_from": None,
            },
        ],
    }
    (entry,) = register_catalog(reg, doc)
    assert entry.status == "draft"
    with pytest.raises(StandardsRegistryError, match="draft_standard"):
        reg.resolve("NY/T 9999@2025")
    with pytest.raises(StandardsRegistryError, match="no_effective_version"):
        reg.current("NY/T 9999", date(2026, 11, 25))


def test_in_force_status_without_effective_date_is_rejected_at_registration():
    with pytest.raises(StandardsRegistryError, match="in_force_status_needs_effective_date"):
        StandardsRegistry().register(replace(_std("v1", date(2000, 1, 1)), effective_from=None))


# ── إصلاحات مراجعة المستشفى لـ#1624 ─────────────────────────────────────


def test_f2_pinning_a_future_edition_without_a_date_is_refused_today():
    reg, _ = _catalog()
    with pytest.raises(StandardsRegistryError, match="not_yet_effective"):
        reg.resolve("GB/T 48026@2026")
    adoption = StandardAdoption(
        "GB/T 48026", "adopted", authority="a", reference="r", adopted_on=date(2026, 1, 1)
    )
    with pytest.raises(StandardsRegistryError, match="not_yet_effective"):
        reg.register_profile(
            ComplianceProfile("P-fut", "YE", ("GB/T 48026@2026",), adoption=(adoption,))
        )


def _binding_report(status, *, adopted_on, adoption_status="adopted", version_status="active"):
    reg = StandardsRegistry()
    reg.register(
        _std(
            "v1",
            date(2000, 1, 1),
            status=version_status,
            superseded_by="TEST-STD@v2" if version_status == "superseded" else None,
        )
    )
    if version_status == "superseded":
        reg.register(_std("v2", date(2020, 1, 1)))
    adoption = StandardAdoption(
        "TEST-STD", adoption_status, authority="MAI", reference="d1", adopted_on=adopted_on
    )
    reg.register_profile(ComplianceProfile("P", "YE", (status,), adoption=(adoption,)))
    return evaluate_profile(reg, "P", [_obs("ece_ds_m", 1.0, "dS/m")], on=ON)


def test_f3_binding_needs_adopted_status_a_past_adoption_date_and_an_in_force_edition():
    assert _binding_report("TEST-STD", adopted_on=date(2026, 1, 1)).legally_binding is True
    assert _binding_report("TEST-STD", adopted_on=None).legally_binding is False
    assert _binding_report("TEST-STD", adopted_on=date(2030, 1, 1)).legally_binding is False
    assert (
        _binding_report(
            "TEST-STD", adopted_on=date(2026, 1, 1), adoption_status="provisional"
        ).legally_binding
        is False
    )
    sup = _binding_report("TEST-STD@v1", adopted_on=date(2026, 1, 1), version_status="superseded")
    assert sup.legally_binding is False
    assert sup.verdict == "incomplete"  # superseded edition is evidence, not a limit in force


def test_f4_the_catalogue_file_is_pinned_by_its_own_hash(tmp_path):
    raw = FARMLAND_AUDIT_CATALOG.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FARMLAND_AUDIT_CATALOG_SHA256
    tampered = tmp_path / "c.json"
    shutil.copy(FARMLAND_AUDIT_CATALOG, tampered)
    tampered.write_bytes(raw.replace(b'"2027-05-01"', b'"2026-05-01"', 1))
    with pytest.raises(StandardsRegistryError, match="catalog_hash_mismatch"):
        load_catalog(tampered, expected_sha256=FARMLAND_AUDIT_CATALOG_SHA256)


def test_f5_a_standard_not_in_force_never_yields_compliant_and_never_crashes():
    withdrawn = replace(HB60_SALINE_SODIC, status="withdrawn")
    obs = [_obs("ece_ds_m", 1.0, "dS/m"), _obs("esp_pct", 5.0, "%")]
    report = evaluate_standards([withdrawn], obs, on=ON)
    assert report.verdict == "incomplete"
    assert {r.reason for r in report.results} == {"standard_not_in_force:withdrawn"}
    assert report.to_dict()["standards"]["USDA-HB60@1954"]["in_force_on_evaluation_date"] is False
    undated = replace(HB60_SALINE_SODIC, status="unresolved", effective_from=None)
    out = evaluate_standards([undated], obs, on=ON).to_dict()
    assert (
        out["verdict"] == "incomplete"
        and out["standards"]["USDA-HB60@1954"]["effective_from"] is None
    )


def test_nit7_boolean_is_not_a_numeric_tightening():
    reg = default_registry()
    with pytest.raises(StandardsRegistryError, match="override_loosens_upper"):
        reg.register_profile(
            _profile(ClauseOverride("USDA-HB60", "saline.ECe", "bool", upper=True))
        )


def test_nit8_a_datetime_observation_date_is_not_evaluated_rather_than_crashing():
    obs = Observation(
        "ece_ds_m", 1.0, "dS/m", source="lab", observed_on=datetime(2026, 10, 1, 12, 0)
    )
    report = evaluate_standards([HB60_SALINE_SODIC], [obs, _obs("esp_pct", 5.0, "%")], on=ON)
    ece = next(r for r in report.results if r.clause_id == "saline.ECe")
    assert (ece.status, ece.reason) == ("not_evaluated", "observation_date_not_a_date")

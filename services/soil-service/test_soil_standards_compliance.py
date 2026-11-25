"""Farmland Phase 2 · 0001 — standards registry + compliance engine contract."""

from dataclasses import replace
from datetime import date

import pytest
from compliance_engine import Observation, classify_band, evaluate_profile, evaluate_standards
from standards_registry import (
    FAO29_WATER_QUALITY,
    HB60_SALINE_SODIC,
    Band,
    Clause,
    ClauseOverride,
    ComplianceProfile,
    Standard,
    StandardsRegistry,
    StandardsRegistryError,
    default_registry,
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
        _std("v1", date(2000, 1, 1), status="draft"),
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

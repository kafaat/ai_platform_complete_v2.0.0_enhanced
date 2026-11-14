"""observed_at في الحالة القانونيّة (قرار المالك 2026-11-14: يُحفَظ النسب الزمنيّ).

كان compose_field_state يقرأ observed_at للحداثة فقط ثمّ يُسقطه: لا to_dict ولا مغلّف
المرحلة 9 (shared/field_runtime_cohesion) يحمله، فـruntime_feature_lineage كتب «المغلّف لا
يحمل observed_at». يفرض هذا الملفّ (نقيّ، بلا قاعدة ولا شبكة):

  * كلّ إشارة ذات قيمة وزمن رصد يُسجَّل زمنها في الحالة، مُطبَّعاً إلى UTC ومرتّباً زمنيّاً.
  * الطابع naive (ومنه التاريخ المجرّد) يُرفَض كـAwareDatetime في AC-1: لا يُسجَّل ويُعلَن.
  * الغائب يبقى غائباً: لا ساعة تملؤه، ولا لحظة التطبيع تُحفَظ كأنّها رصد.
  * القيمة ثابتة بعد تسجيلها، ويغطّيها state_id.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone

import pytest
from core.agronomic_state_engine import (
    CanonicalFieldState,
    SignalInput,
    canonical_observed_at,
    compose_field_state,
)
from core.field_intelligence_coordinator import CollectorResult, normalize_signals

from shared.field_runtime_cohesion import create_canonical_state_envelope

pytestmark = pytest.mark.unit

_ADEN = timezone(timedelta(hours=3))
_NDVI_AT = "2026-08-03T09:30:00+03:00"  # = 06:30Z
_EC_AT = "2026-07-20T08:00:00Z"
_RVI_AT = "2026-08-02T21:00:00+00:00"


def _signals() -> list[SignalInput]:
    return [
        SignalInput(source="ndvi", value=0.62, observed_at=_NDVI_AT),
        SignalInput(source="soil_ec", value=2.1, confidence="high", observed_at=_EC_AT),
        SignalInput(source="rvi", value=0.55, observed_at=_RVI_AT),
    ]


def _state(signals: list[SignalInput] | None = None) -> CanonicalFieldState:
    return compose_field_state("field-1", signals or _signals(), tenant_id="tenant-1")


def test_state_records_each_signal_observed_at_in_utc_and_in_time_order():
    state = _state()
    assert state.signal_observations == (
        ("soil_ec", "2026-07-20T08:00:00+00:00"),
        ("rvi", "2026-08-02T21:00:00+00:00"),
        ("ndvi", "2026-08-03T06:30:00+00:00"),
    )


def test_order_does_not_depend_on_signal_arrival_order():
    assert _state(list(reversed(_signals()))).signal_observations == _state().signal_observations


def test_observations_survive_serialisation_and_replay():
    state = _state()
    d = state.to_dict()
    assert d["signal_observations"] == [
        {"source": "soil_ec", "observed_at": "2026-07-20T08:00:00+00:00"},
        {"source": "rvi", "observed_at": "2026-08-02T21:00:00+00:00"},
        {"source": "ndvi", "observed_at": "2026-08-03T06:30:00+00:00"},
    ]
    assert CanonicalFieldState.from_dict(d).signal_observations == state.signal_observations


def test_state_from_before_the_field_existed_replays_with_no_observations():
    d = _state().to_dict()
    del d["signal_observations"]
    assert CanonicalFieldState.from_dict(d).signal_observations == ()


@pytest.mark.parametrize(
    "value",
    ["2026-08-03T09:30:00", "2026-08-03", datetime(2026, 8, 3, 9, 30), "not-a-date", "", 17],
)
def test_naive_or_invalid_observed_at_is_refused(value):
    with pytest.raises(ValueError):
        canonical_observed_at(value)


def test_aware_datetime_is_normalised_to_utc():
    assert canonical_observed_at(datetime(2026, 8, 3, 9, 30, tzinfo=_ADEN)) == (
        "2026-08-03T06:30:00+00:00"
    )


def test_naive_signal_time_is_not_recorded_and_is_declared():
    signals = _signals()
    signals[0] = SignalInput(source="ndvi", value=0.62, observed_at="2026-08-03T09:30:00")
    state = _state(signals)
    assert [s for s, _ in state.signal_observations] == ["soil_ec", "rvi"]
    refused = [
        c
        for c in state.contradictions
        if isinstance(c, dict) and c.get("type") == "observed_at_refused"
    ]
    assert refused and refused[0]["sources"] == ["ndvi"]


def test_naive_time_in_a_stored_state_is_refused_on_replay():
    d = _state().to_dict()
    d["signal_observations"][0]["observed_at"] = "2026-07-20T08:00:00"
    with pytest.raises(ValueError):
        CanonicalFieldState.from_dict(d)


def test_missing_time_stays_missing_and_is_not_filled_from_the_clock():
    collected = CollectorResult(raw={"sensing": {"ndvi": 0.6}, "soil": {"ec_dsm": 2.0}})
    signals = normalize_signals(collected)
    assert {s.source: s.observed_at for s in signals} == {"ndvi": None, "soil_ec": None}
    assert _state(signals).signal_observations == ()


def test_signal_without_value_records_no_time():
    signals = [*_signals(), SignalInput(source="ndre", value=None, observed_at=_NDVI_AT)]
    assert "ndre" not in {s for s, _ in _state(signals).signal_observations}


def test_recorded_observations_are_immutable():
    state = _state()
    recorded = state.signal_observations
    with pytest.raises(AttributeError):
        state.signal_observations = [("ndvi", "2026-01-01T00:00:00+00:00")]
    state.to_dict()["signal_observations"].clear()
    assert state.signal_observations == recorded
    # إعادة تسجيل القيمة نفسها ليست تعديلاً.
    state.signal_observations = list(recorded)
    assert state.signal_observations == recorded


def test_state_id_covers_observed_at():
    base = create_canonical_state_envelope(_state().to_dict() | {"generated_at": "g"})
    same = create_canonical_state_envelope(_state().to_dict() | {"generated_at": "g"})
    later = _signals()
    later[0] = SignalInput(source="ndvi", value=0.62, observed_at="2026-08-04T09:30:00+03:00")
    moved = create_canonical_state_envelope(_state(later).to_dict() | {"generated_at": "g"})
    assert base["state_id"] == same["state_id"]
    assert moved["state_id"] != base["state_id"]
    assert moved["state"]["operational_truths"] == base["state"]["operational_truths"]


def test_envelope_carries_observations_to_the_phase9_runtime():
    state = _state()
    envelope = create_canonical_state_envelope(state)
    assert envelope["state"]["signal_observations"] == state.to_dict()["signal_observations"]
    for entry in envelope["state"]["signal_observations"]:
        parsed = datetime.fromisoformat(entry["observed_at"])
        assert parsed.utcoffset() == UTC.utcoffset(None)


def test_empty_observations_are_immutable_from_construction():
    state = _state([SignalInput(source="ndvi", value=0.62)])
    assert state.signal_observations == ()
    with pytest.raises(AttributeError):
        state.signal_observations = [("ndvi", "2026-08-03T06:30:00+00:00")]


def test_raw_dict_path_normalises_observations_before_hashing():
    d = _state().to_dict() | {"generated_at": "g"}
    shifted = copy.deepcopy(d)
    for entry in shifted["signal_observations"]:
        entry["observed_at"] = (
            datetime.fromisoformat(entry["observed_at"]).astimezone(_ADEN).isoformat()
        )
    shifted["signal_observations"].reverse()
    assert shifted["signal_observations"] != d["signal_observations"]
    a, b = create_canonical_state_envelope(d), create_canonical_state_envelope(shifted)
    assert a["state_id"] == b["state_id"]
    assert b["state"]["signal_observations"] == d["signal_observations"]


def test_raw_dict_path_refuses_a_naive_observation():
    d = _state().to_dict()
    d["signal_observations"][0]["observed_at"] = "2026-07-20T08:00:00"
    with pytest.raises(ValueError):
        create_canonical_state_envelope(d)


def test_future_observation_is_not_recorded_and_is_not_fresh():
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    signals = [*_signals(), SignalInput(source="ndre", value=0.4, observed_at=future)]
    state = _state(signals)
    assert "ndre" not in {s for s, _ in state.signal_observations}
    declared = [
        c
        for c in state.contradictions
        if isinstance(c, dict) and c.get("type") == "future_observation"
    ]
    assert declared and declared[0]["sources"] == ["ndre"]


def _weather_signals(forecast_at: str) -> list[SignalInput]:
    collected = CollectorResult(raw={"weather": {"heat_risk": 0.3, "forecast_at": forecast_at}})
    return normalize_signals(collected)


def test_weather_forecast_time_is_not_recorded_as_an_observation():
    forecast = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    signals = _weather_signals(forecast)
    assert [(s.source, s.observed_at, s.forecast_at) for s in signals] == [
        ("weather", None, forecast)
    ]
    state = _state([*_signals(), *signals])
    assert "weather" not in {s for s, _ in state.signal_observations}
    flagged = {
        src
        for c in state.contradictions
        if isinstance(c, dict) and c.get("type") in ("future_observation", "stale_observation")
        for src in c["sources"]
    }
    assert "weather" not in flagged  # توقّع لاحق ليس رصداً مستقبليّاً ولا قديماً


def test_an_old_forecast_is_still_stale():
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    state = _state(_weather_signals(old))
    stale = [
        c
        for c in state.contradictions
        if isinstance(c, dict) and c.get("type") == "stale_observation"
    ]
    assert stale and "weather" in stale[0]["sources"]
    assert state.signal_observations == ()

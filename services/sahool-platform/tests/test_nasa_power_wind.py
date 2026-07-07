"""تحقّق — تفكيك ردّ NASA POWER لتاريخ الرياح (منطق صرف) + وصله بوردة الرياح.

- parse_wind_history يستخرج (اتّجاه, سرعة) ويُسقِط قيمة الحارس -999 بصدق.
- ردّ شاذّ/فارغ ⇒ None (لا تلفيق).
- السلسلة المُستخرَجة تُغذّي wind_rose → prevailing → windbreak_recommendation.
"""

from __future__ import annotations

from api.connectors.nasa_power import parse_wind_history
from core.wind_geometry import wind_rose, windbreak_recommendation


def _power_response(wd: dict, ws: dict | None = None) -> dict:
    params: dict = {"WD10M": wd}
    if ws is not None:
        params["WS10M"] = ws
    return {"properties": {"parameter": params}}


def test_parse_drops_fill_value_and_pairs_speed():
    resp = _power_response(
        {"20260101": 315.0, "20260102": -999.0, "20260103": 300.0},
        {"20260101": 6.2, "20260102": 5.0, "20260103": -999.0},
    )
    out = parse_wind_history(resp)
    # اليوم الثاني اتّجاهه حارس ⇒ يُسقَط كليّاً؛ الثالث سرعته حارس ⇒ اتّجاه يبقى وسرعة None.
    assert out == [(315.0, 6.2), (300.0, None)]


def test_parse_honest_none_on_malformed():
    assert parse_wind_history(None) is None
    assert parse_wind_history({}) is None
    assert parse_wind_history({"properties": {"parameter": {}}}) is None
    # كلّها قيم حارس ⇒ لا سلسلة ⇒ None.
    assert parse_wind_history(_power_response({"20260101": -999.0})) is None


def test_parsed_history_feeds_windbreak_engine():
    # سلسلة شماليّة غربيّة سائدة (≥min_obs) ⇒ وردة رياح ⇒ توصية مصدّ عموديّة.
    wd = {
        f"2026010{i}": deg for i, deg in enumerate([315, 310, 320, 315, 300, 330, 315, 305, 318], 1)
    }
    obs = parse_wind_history(_power_response(wd))
    assert obs is not None and len(obs) == 9
    rose = wind_rose(obs)
    assert rose["prevailing"]["key"] in {"NW", "WNW", "NNW"}
    rec = windbreak_recommendation(rose["prevailing_deg"], tree_height_m=4.0)
    assert rec["status"] == "ok" and rec["protected_downwind_m"] == 40.0

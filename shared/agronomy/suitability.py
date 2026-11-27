"""Common linear response to optimal and tolerable intervals."""


def range_score(value: float, opt: tuple[float, float], ok: tuple[float, float]) -> float:
    """1.0 داخل النطاق الأمثل؛ يتناقص خطّيّاً إلى 0 عند حدّ المقبول؛ 0 خارجه."""
    lo_opt, hi_opt = opt
    lo_ok, hi_ok = ok
    if lo_opt <= value <= hi_opt:
        return 1.0
    if value < lo_opt:
        if value <= lo_ok:
            return 0.0
        return (value - lo_ok) / (lo_opt - lo_ok)
    # value > hi_opt
    if value >= hi_ok:
        return 0.0
    return (hi_ok - value) / (hi_ok - hi_opt)

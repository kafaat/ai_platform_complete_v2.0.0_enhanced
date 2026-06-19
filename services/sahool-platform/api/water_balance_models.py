"""api/water_balance_models.py — نموذج طلب «ميزان الماء» (FAO-56 Water Balance)
==============================================================================
شريحة من تفكيك ``api/main.py`` (البند B1): استُخرج ``WaterBalanceRequest`` حرفيّاً
من ``main.py`` إلى وحدته الخاصّة ليستورده الموجِّه ``api/routers/water_balance.py``
مباشرةً (لا عبر ``api.main``)، تقليلاً لحجم ``main.py`` ولفكّ الارتباط الدائريّ.

self-contained: يعتمد على pydantic + الأنواع المعياريّة فقط.
"""

from __future__ import annotations

from pydantic import BaseModel


class WaterBalanceRequest(BaseModel):
    crop: str
    stage: str = "mid"  # initial|development|mid|late
    t_min_c: float
    t_max_c: float
    rain_mm: float = 0.0
    ndvi: float | None = None  # إن توفّر ⇒ Kc ديناميكيّ من الغطاء (وإلّا ثابت بالمرحلة)
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int = 100

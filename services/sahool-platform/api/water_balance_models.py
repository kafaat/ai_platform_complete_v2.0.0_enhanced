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
    forecast_rain_mm: float | None = None  # مطر متوقّع خلال النافذة ⇒ تأجيل (لا خصم كمّيّة)
    forecast_window_days: int = 3
    forecast_confidence: float = 1.0  # احتماليّة التنبّؤ [0,1] — تُضرب في المطر المتوقّع
    forecast_infiltration: float = 0.7  # عامل ترشّح المطر للجذور [0,1]
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int = 100
    # ── تحليل الملوحة (اختياريّ) — يُفعّل مسار الملوحة تلقائيّاً عند توفّر تحليل موثوق ──
    # صدق: غيابها ⇒ حساب بلا ملوحة (السلوك القائم تماماً). توفّرها ⇒ يقرّر salinity_policy
    # تلقائيّاً (ECe/ECw حديثة <365 يوم + ثقة ≥0.8، أو ECe>2/ECw>1.5/محصول حسّاس).
    soil_ece: float | None = None  # ملوحة مستخلَص عجينة الإشباع (dS/m) — من تحليل تربة مخبريّ
    water_ecw: float | None = None  # توصيل كهربائيّ لمياه الريّ (dS/m) — من تحليل ماء مخبريّ
    analysis_age_days: int | None = None  # عمر أحدث تحليل (يوم) — الحداثة شرط للتفعيل
    analysis_confidence: float | None = None  # ثقة التحليل [0,1] — ≥0.8 شرط للتفعيل
    crop_sensitive: bool = False  # محصول حسّاس جدّاً للملوحة (حمضيّات/عنب/فستق)
    saline_region: bool = False  # حقل في منطقة معروفة بالملوحة (للتنبيه عند البيانات القديمة)

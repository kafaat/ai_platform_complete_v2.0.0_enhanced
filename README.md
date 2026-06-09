# 🌿 SAHOOL v9 — التنفيذ الحقيقي

## ما الذي تغيّر؟

| الخدمة | قبل (محاكاة) | بعد (حقيقي) |
|--------|-------------|-------------|
| NDVI | `hash(field_id) % 100` | Sentinel Hub Process API |
| ET0 | `random.gauss(4, 1)` | Open-Meteo ERA5 Reanalysis |
| GDD | `hash(field_id) % 500` | Open-Meteo Tmax/Tmin حقيقي |
| AGB | ثابت | Random Forest R²=0.89 (من الورقة) |
| Kc | ثابت 1.15 | FAO-56 Kc curve حسب يوم الموسم |
| WOFOST | random yield | WOFOST-RUE كامل + Beer-Lambert LAI |
| SMTP | `smtplib` blocking | `aiosmtplib` non-blocking |

---

## مصادر البيانات

### ① Open-Meteo (مجاني — بلا API key)
```
https://archive-api.open-meteo.com/v1/archive
المتغيرات: tmax, tmin, rain, radiation, ET0_FAO
الدقة الزمنية: يومية
الغطاء: 1940 → الآن (ERA5 Reanalysis)
البيانات: حقيقية 100% (إعادة تحليل ECMWF)
```

### ② Sentinel Hub (مجاني للأبحاث)
```
https://services.sentinel-hub.com
الصور: Sentinel-2 L2A (BOA — تصحيح جوي)
الدقة: 10m (B04, B08) | 20m (B11, B12)
التغطية: كل 5 أيام
الـ evalscript: يحسب NDVI/EVI/SAVI/NDWI/GNDVI/LAI مباشرة
```
للحصول على مفتاح مجاني: https://www.sentinel-hub.com/develop/api/

### ③ WOFOST-RUE (نموذج داخلي)
```
المعاملات: من WOFOST crop database + FAO-56 Table 11
الطقس: Open-Meteo (حقيقي)
المخرجات: GDD, LAI, biomass, yield, ETc
```

### ④ AGB Random Forest (من الورقة البحثية)
```
المرجع: Plant Methods 2023 (IMG_2330)
R² = 0.89, RMSE = 9.1 t/ha
الميزات: NDVI + EVI + GNDVI (Sentinel-2) + VV/VH (Sentinel-1)
المعادلة: Equation 4, Table 3
```

---

## التثبيت والتشغيل

```bash
# تثبيت
pip install -r requirements_real.txt

# اختبار الاتصال بـ Open-Meteo (مجاني)
python tests/test_real_data.py

# تشغيل vegetation service
SENTINELHUB_CLIENT_ID=your_id \
SENTINELHUB_CLIENT_SECRET=your_secret \
uvicorn sentinel_hub.vegetation_real:app --port 8090

# بدون Sentinel Hub (Open-Meteo فقط)
uvicorn sentinel_hub.vegetation_real:app --port 8090

# تشغيل indicators service
VEGETATION_URL=http://localhost:8090 \
uvicorn vegetation_real.indicators_real:app --port 8091
```

---

## النطاقات المتوقعة (البيضاء، اليمن)

| المؤشر | الشتاء (يناير) | الصيف (يوليو) |
|--------|---------------|--------------|
| NDVI   | 0.45 – 0.75   | 0.15 – 0.35  |
| ET0    | 3.5 – 5 mm/d  | 7 – 9 mm/d   |
| GDD/day| 8 – 13 °C·d   | 22 – 28 °C·d |
| Rain   | 5 – 20 mm/wk  | 30 – 60 mm/wk|

---

## الفرق بين الوضعين

```
بدون SENTINELHUB_CLIENT_ID:
  → Open-Meteo يوفر طقساً حقيقياً
  → NDVI مشتق من بيانات المناخ (دقة ≈ ±0.12)
  → مجاني تماماً

مع SENTINELHUB_CLIENT_ID:
  → صور Sentinel-2 حقيقية (دقة 10m)
  → NDVI حقيقي (دقة ±0.02)
  → مجاني حتى 30,000 processing units/شهر
```

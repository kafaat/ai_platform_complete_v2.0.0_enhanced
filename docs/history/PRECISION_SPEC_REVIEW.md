# مراجعة المستندَين ٨ و ٩ — SAHOOL Precision Farming v1.0 Spec

> **المنهجيّة:** هذان المستندان أكثر "buildable" من المستندات الستّة السابقة
> (التي كانت theater). هما blueprint تقني عملي. لكن **التطبيق الأعمى** سيُضيع
> ستّة أشهر في بناء أشياء غير ضروريّة لمرحلة الـpilot.
>
> هذه المراجعة تطابق كل بند مع الواقع:
>   1. ما هو **موجود** فعلاً (ولا داعي لإعادة بنائه)
>   2. ما هو **يصلح للتنفيذ** (نضيفه)
>   3. ما هو **premature** (نؤجّله بـtrigger صريح)
>   4. ما هو **غير مناسب** للسياق (نرفضه)

---

## ١. مطابقة الـ٦ طبقات المعماريّة مع ما لدينا

### A. Experience Layer (Frontends)
| المطلوب | لدينا | الحكم |
|---------|-------|------|
| Flutter Mobile (Owner App) | **React Native** بـ٦٧ ملف | ⚠ Flutter سيتطلّب إعادة كتابة كاملة — **نرفض التحوّل** |
| Flutter Tablet (Cab App) | غير موجود | ❌ premature — يحتاج Drive hardware |
| React Web Dashboard | `sahool_frontend/` (React + Vite + MapLibre) | ✓ موجود |

**القرار:** الالتزام بـReact Native للموبايل. التحوّل إلى Flutter سيُضيع ٣ أشهر بدون فائدة وظيفيّة.

### B. Edge Layer (SAHOOL Drive — Raspberry Pi)
| المطلوب | لدينا | الحكم |
|---------|-------|------|
| Raspberry Pi 4 + CAN bus HAT | غير موجود | ❌ premature لـpilot |
| BLE Gateway | غير موجود | ❌ premature |
| Local SQLite buffer | غير موجود | ❌ يحتاج Drive أوّلاً |

**القرار:** نؤجّل كل Edge Layer. **Trigger:** ١٠+ مزارعين فعليّين + معدّات لديها CAN bus.
**السبب:** الغالبيّة العظمى من المزارعين اليمنيّين يستخدمون معدّات قديمة بدون CAN bus.

### C. Data Ingestion Layer
| المطلوب | لدينا | الحكم |
|---------|-------|------|
| Satellite ingestion (Sentinel) | `sentinel-hub-mcp` + `vegetation-analysis-service` | ✓ موجود |
| GIS ingestion (Shapefile/GeoJSON/KML) | جزئي — GeoJSON يعمل، Shapefile لا | ⚠ نضيف Shapefile parser |
| Sensor ingestion (MQTT/soil) | غير موجود | ⚠ تأجيل |
| CAN bus ingestion | يحتاج Drive | ❌ مع Drive |

### D. Core Backend Layer
| المطلوب | لدينا | الحكم |
|---------|-------|------|
| FastAPI services | ✓ ٢٩ services | ✅ |
| PostgreSQL + PostGIS | ✓ migrations v8-v11 | ✅ |
| Redis | ✓ في auth + tts | ✅ |
| MinIO | ✓ على localhost (آمن) | ✅ |
| NATS | ✓ في ٤ services | ✅ |
| Command Store | ✓ migration v10 | ✅ بُني في الجلسة الحاليّة |
| Events Bus | ✓ migration v11 | ✅ بُني الآن |

### E. Intelligence Layer (AI Core)
| المطلوب | لدينا | الحكم |
|---------|-------|------|
| Yield prediction (XGBoost) | `yield_heuristics.py` (قواعد، لا ML) | ⚠ المستند يقول XGBoost — نؤجّل |
| Irrigation scheduling (ET0 + soil moisture) | قواعد بسيطة في supervisor-agent | ⚠ يحتاج توسعة |
| Fertilizer recommendation (NPK) | `prescriptions.py` ✓ | ✅ موجود |
| Pest warning (weather-based) | guardrails-engine جزئي | ⚠ يحتاج توسعة |
| Crop selection engine | غير موجود | ⚠ تأجيل |

**النقطة الحرجة:** المستند ٨ نفسه يقول في "Critical Risks":
> "AI claims → Must start rule-based, not ML-first"

هذا يطابق نهجنا تماماً. الـXGBoost mention في القسم ٧ يتناقض مع الـrisk note. نأخذ بـrisk note.

### F. Decision & Reporting Layer
| المطلوب | لدينا | الحكم |
|---------|-------|------|
| Reports engine | `reports.py` ✓ بُني الآن | ✅ |
| TrueUp engine | غير موجود — مهمّ! | ⚠ **نبنيه (الميزة الأبرز)** |
| Notifications (WhatsApp/SMS/Push) | `notification-agent` موجود | ✓ يحتاج WhatsApp API |

---

## ٢. الـ١٥ خطوة الـMVP من المستند ٩

### الخطوة ١: تسجيل الحساب
| المطلوب | الواقع | الحكم |
|---------|--------|------|
| تسجيل بالهاتف +967 OTP | `auth` service موجود لكن phone+OTP غير مُفعّل | ⚠ يحتاج twilio أو OTP محلّي |
| Google/Apple login | غير موجود | ⚠ تأجيل |
| نوع المزرعة (تجارية/عائلية/تعاونية) | غير موجود في الـschema | 🟢 إضافة بسيطة |
| الأقاليم المناخيّة | غير موجود | 🟢 lookup table بسيط |

### الخطوة ٢: إضافة الحقل
| المطلوب | الواقع | الحكم |
|---------|--------|------|
| خريطة تفاعليّة RTL | `MapLibreView.tsx` ✓ + `sahool_field_drawing.html` ✓ | ✅ |
| أدوات رسم (مضلع/مستطيل/دائرة) | polygon + pivot + sector + tower ✓ | ✅ |
| استيراد KML/GeoJSON/ShapeFile | GeoJSON ✓، KML ⚠، Shapefile ❌ | ⚠ نضيف |
| حساب المساحة | PostGIS trigger ✓ | ✅ |
| نوع التربة + الري | في SoilFormScreen ✓ | ✅ |
| ربط محطة طقس | غير موجود | ⚠ بسيط: nearest station |

### الخطوة ٣: إدارة الحقول
| المطلوب | الواقع | الحكم |
|---------|--------|------|
| لوحة تحكم لكل حقل | شاشة FieldDetail ✓ | ✅ |
| تقسيم لـ zones (NDVI) | في `prescriptions.py` ✓ | ✅ |
| تاريخ العمليّات | events table ✓ بُني الآن | ✅ |

### الخطوات ٤-٦
- صندوق البيانات → جزئي (sentinel ✓، drone ❌، sensors ❌)
- المشاركة (advisor) → غير موجود — **مهمّ، نبنيه**
- تحليل الإنتاجيّة → موجود (reports.py + yield_heuristics.py)

---

## ٣. الميزات الجديدة من المستندَين التي نبنيها فعلاً

### ✅ TrueUp Engine (الميزة الأبرز من FieldView)

من المستند ٩:
> ```
> POST /api/v1/fields/{field_id}/operations/{operation_id}/trueup
> Body: { true_up_weight_kg, true_up_moisture_pct, notes }
> ```
> ```
> k_new = true_up_weight / measured_weight
> Y_adjusted = Y_raw * k_new
> ```

**هذه ميزة حقيقيّة ولها قيمة محسوسة للمزارع.** نبنيها.

### ✅ Sharing Keys (للـadvisor + dealer)

من المستند ٩:
> "دعوة مستشار زراعي (قراءة / تحرير / إدارة)"
> "Sharing Key: scope: read / read_write, expires_at"

**مفيد جدّاً للسياق اليمني** (المهندس الزراعي قد يخدم ٢٠ مزرعة). نبنيه.

### ✅ Custom Reports — Polygon Region Reports

من المستند ٩:
> "Field Region Report: رسم مضلع → تقرير yield/moisture للمنطقة فقط"

موجود لدينا بشكل عام لكن **بدون polygon-based slicing**. نضيفه.

### ✅ Shapefile import

موجود في الـrequirements لكن غير مُنفَّذ. مهمّ للـadvisors.

---

## ٤. ما رفضنا من المستندَين (بصدق + مبرّر)

### ❌ Flutter migration
**الادّعاء:** Flutter mobile + tablet.
**الواقع:** لدينا React Native بـ٦٧ ملف + ٠ أخطاء + tests. التحوّل = ٣ أشهر بدون قيمة.
**التوصية:** الإبقاء على RN. هذا ليس عيب technical، هو قرار براغماتي.

### ❌ SAHOOL Drive (Raspberry Pi) في v1
**الادّعاء:** كل مزارع يحصل على Raspberry Pi بـ$100.
**الواقع:**
- الغالبيّة العظمى من معدّات اليمن **بدون CAN bus** (جرّارات قديمة)
- الـlogistics لتوزيع ١٠٠ Raspberry Pi في اليمن غير محلولة
- BLE pairing setup سيُحبط ٨٠٪ من المزارعين
- الـ$100 × ١٠٠ مزارع = $١٠،٠٠٠ بلا ROI واضح في الـpilot

**التأجيل بـtrigger صريح:** بعد ١٠٠ مزارع نشط + معدّات حديثة في عيّنة موثّقة.

### ❌ Closed-Loop Auto-Irrigation
المستند ٧ ادّعى هذا، المستندَان ٨-٩ يلمّحان إليه.
**نرفض autonomous execution.** الـAI يقترح، المزارع يقرّر.

### ❌ Carbon Calculator + Market Engine v1
المستند ٩:
> "8. Carbon Calculator: بصمة كربونية، اعتمادات"
> "Market Report: أسعار + توصيات بيع"

**ليست أولويّة pilot.** الـcarbon market لا يعمل في اليمن. الـmarket data تحتاج بنية لا توجد بعد.

### ❌ WhatsApp Business API كـrequirement
المستند ٩ يصرّ على WhatsApp.
**الواقع:** WhatsApp Business API يتطلّب:
- موافقة Meta (يستغرق أسابيع)
- contract مع BSP (Business Solution Provider)
- $0.005-$0.08 لكل رسالة

**البديل:** Push notifications أوّلاً (مجّاني، فوري). WhatsApp **اختياري بعد** pilot.

### ❌ E2E test claims (1000 concurrent sync)
المستند ٩:
> "test_1000_concurrent_sync: 1000 جهاز يتزامن في نفس الوقت"
> "test_remoteview_latency: 500 اتصال WebSocket → latency < 2s"

**لـpilot بـ١٠٠ مزارع، هذا over-engineering.** الـ١٠،٠٠٠ concurrent connections في app بـ١٠٠ user = bug في الـclient. نُؤجّل load tests إلى مرحلة scale.

---

## ٥. الإصلاحات الأخيرة المستفادة من المستندَين

### المعايير الواقعيّة (نتبنّاها)
| المعيار | الهدف من المستند ٩ | الواقعيّة |
|---------|------|----------|
| Sync latency | <10s | ✅ مع EventBus + outbox |
| Map render | <3s | ⚠ نقيس |
| Offline duration | 48h | ✅ syncEngine.ts + secureStorage |
| TrueUp error | <5% | ⚠ نُنفّذ ونقيس |
| RemoteView latency | <2s | ❌ مُؤجَّل (تحتاج WebSocket infra) |
| BLE latency | <1s | ❌ مع Drive |
| Field Region Report | <3s | ⚠ نُنفّذ |

### العقد الذي نلتزم به
الـpilot v1 يضمن:
- ✅ Offline 48h
- ✅ Sync latency <10s (test sequenced)
- ✅ Field Region Report <3s
- ✅ TrueUp error <5%
- ✅ Arabic RTL 100%
- ❌ لا BLE/Drive (مُؤجَّل)
- ❌ لا RemoteView (مُؤجَّل)

---

## ٦. الخطّة العمليّة (Next 4 sessions)

### Session A — TrueUp Engine + Sharing Keys (أعلى ROI)
1. `migrations/v12_trueup_sharing.sql` — `operations`, `trueup_calibrations`, `sharing_keys`
2. `api/trueup.py` — k_new calculation + yield re-adjustment + event emission
3. `api/sharing.py` — generate key, scope (read/write), expiration
4. Tests للـpiyade kalman recalc

### Session B — Reports Enhancements
1. Polygon-based Region Reports
2. Shapefile parser (pyshp)
3. KML/GeoJSON exporter
4. Mobile screens للـreports

### Session C — Onboarding flow
1. Phone OTP (محلّي أوّلاً)
2. Farm type + climate zone
3. Field creation wizard (٦ خطوات)
4. Data Inbox preview (status فقط، بدون connectivity)

### Session D — AI Improvements
1. ET0-based irrigation suggestions (لا closed-loop)
2. Pest warning من weather + crop stage
3. Crop selection advisor (rule-based)

---

## ٧. الخلاصة الصادقة

### ما المستندان أضافاه فعلاً
- ✅ **TrueUp Engine** — ميزة قيّمة وقابلة للبناء
- ✅ **Sharing Keys** — مفيد للسياق العربي
- ✅ **Polygon Region Reports** — تحسين عملي
- ✅ **Shapefile import** — مفيد للـadvisors

### ما طرحاه بـ"يجب أن"
- ❌ Flutter — نرفض، RN كافٍ
- ❌ Raspberry Pi Drive في v1 — نؤجّل (logistics)
- ❌ XGBoost yield prediction — نبدأ بقواعد كما يوصي المستند ٨ نفسه
- ❌ Carbon Calculator + Market — premature

### السؤال المنهجي
> "هذه المنصّة ليست تطبيق واحد — هي Distributed Agricultural Operating System (AgriOS)"

هذا التأطير يعود مرّة أخرى. الواقع: **منصّة زراعيّة جيّدة لـ١٠٠ مزارع يمني**.
الـ"AgriOS" framing يميل نحو over-engineering. نرفضه بصدق.

### ما تطبّقه على نهجنا
- ✅ نحافظ على human-in-the-loop
- ✅ نبني بـrule-based قبل ML
- ✅ نبدأ بـpilot صغير قبل scale
- ✅ نسمّي الأشياء باسمها (لا "AgriOS"، نقول "منصّة")

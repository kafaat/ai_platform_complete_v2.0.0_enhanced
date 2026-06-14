# مواصفة تصميم واجهة «تطبيق الحقل» (طراز FieldView) — SAHOOL

> **الحالة:** مواصفة مرجعيّة (Design Spec). لا تُغيّر سلوكاً ولا أرقاماً زراعيّة.
> **المصدر:** نموذج الواجهة المهنيّ الذي اعتمده المستخدم مرجعاً (طراز Climate
> FieldView — تربة/ذهب/أخضر دافئ، 14 شاشة موبايل).
> **الغاية:** تثبيت نظام التصميم + خريطة ربط كلّ شاشة بـ**API/هوك حقيقيّ** في
> سهول، قبل أيّ تنفيذ — فالتنفيذ يصبح كسوةً موجَّهة لا اجتهاداً.
> **تنفيذ مرجعيّ اختياريّ:** PR #161 (فرع `feat/ds-fieldapp-skin`، **مسوّدة**)
> يجسّد نظام التصميم + شاشة إثبات واحدة (`FieldAppPreview`) — يُبنى ويُفحَص؛
> يُسحَب منه عند اعتماد المواصفة.

---

## 1) مبادئ التصميم

| المبدأ | التطبيق في سهول |
|---|---|
| **RTL أوّلاً** | التطبيق `dir="rtl"` عالميّاً؛ نستخدم خصائص CSS المنطقيّة (`marginInlineStart`، `insetInlineStart`) لا يمين/يسار ثابت. أسهم «التقدّم» = `ChevronLeft`. |
| **صدق البيانات** | لا بطاقات وهميّة؛ كلّ قيمة من API حقيقيّ. غياب البيانات ⇒ حالة فارغة/خطأ صريحة (لا تلفيق). |
| **طبقة موازية** | ثيم «تطبيق الحقل» الفاتح الدافئ لا يستبدل الثيم الداكن القائم — يكسو شاشات الموبايل تدريجيّاً. |
| **العربيّة الزراعيّة** | مصطلحات الحقل/المؤشّرات/الأنواء بالعربيّة الفصحى المعتمدة في المنصّة. |

---

## 2) رموز التصميم (Design Tokens)

ملف مرجعيّ: `frontend/src/components/ds/tokens.ts`.

### الألوان الأساسيّة (مؤكّدة من النموذج)
| الرمز | القيمة | الاستعمال |
|---|---|---|
| `brown` | `#2C1A0E` | نصّ رئيسيّ/رؤوس داكنة (تربة عميقة) |
| `brownSoft` | `#5B4636` | نصّ ثانويّ داكن |
| `gold` | `#E8A020` | لون الإجراء/التمييز (CTA، تبويب نشط، FAB) |
| `goldSoft` | `#F6C760` | خلفيّات وسوم ذهبيّة |
| `green` | `#3EB050` | المحصول السليم / نجاح |
| `greenDark` | `#2E7D32` | أخضر داكن |
| `cream` | `#FBF7F0` | خلفيّة الصفحة (فاتح دافئ) |
| `card` | `#FFFFFF` | سطح البطاقة |
| `line` | `#E8DFD2` | خطّ فاصل شعريّ |
| `ink` / `muted` / `faint` | `#2C1A0E` / `#8A7B6B` / `#B8AB9A` | نصّ رئيسيّ/ثانويّ/خافت |

### منحدر NDVI (ستّ درجات)
| الرمز | القيمة | المدى |
|---|---|---|
| `ndvi1` | `#C0392B` | 0.00–0.20 (إجهاد شديد/تربة عارية) |
| `ndvi2` | `#E67E22` | 0.20–0.35 |
| `ndvi3` | `#F1C40F` | 0.35–0.50 |
| `ndvi4` | `#A3CB38` | 0.50–0.65 |
| `ndvi5` | `#3EB050` | 0.65–0.80 (صحّيّ) |
| `ndvi6` | `#16794A` | 0.80–1.00 (كثيف) |

> **ملاحظة صادقة:** درجات منتصف المنحدر (`ndvi2..ndvi4`) لوحة NDVI زراعيّة معياريّة
> قابلة للضبط الدقيق من لقطة المستخدم؛ موثّقة كذلك في الكود (لا اختراع صامت).

### الحالات والمساعِدات
- نغمات: `ok` / `warn` / `danger` / `info` / `neutral` + خلفيّاتها الباهتة (`*Bg`).
- دوالّ: `toneColors(tone)` · `ndviColor(v)` · `severityTone(severity)`.
- `RADIUS` = {sm:8, md:12, lg:16, pill:999} · `SPACE` = {xs:4, sm:8, md:12, lg:16, xl:24}.

---

## 3) المكوّنات الذرّيّة (Atoms)

ملف مرجعيّ: `frontend/src/components/ds/atoms.tsx` (مكتوبة الأنواع، واعية RTL).

| المكوّن | الخصائص (Props) | الدور |
|---|---|---|
| `Card` | `children, onClick?, pad?, style?, className?` | سطح بطاقة (حدّ + نصف قطر + حشو) |
| `SectionLabel` | `children, action?` | عنوان قسم صغير + إجراء يمين |
| `Pill` | `children, tone?, icon?` | وسم صغير ملوّن بالنغمة |
| `Badge` | `tone?, children` | نقطة حالة + نصّ |
| `StatBox` | `label, value, unit?, color?, icon?` | إحصاء (تسمية + قيمة كبيرة + وحدة) |
| `ProgressBar` | `value (0..1), color?, height?` | شريط تقدّم (NDVI/إنجاز) |
| `Row` | `label, value?, icon?, onClick?, tone?` | صفّ تسمية⟵قيمة + سهم |
| `TabBar<TId>` | `tabs[{id,label,icon?}], active, onChange` | تبويبات أفقيّة (generic) |
| `FAB` | `icon, onClick?, label?` | زرّ إجراء عائم |
| `BottomSheet` | `open, onClose, title?, children` | لوح منزلق سفليّ |

---

## 4) خريطة الشاشات ← API/هوك حقيقيّ في سهول

الجدول يربط شاشات النموذج الـ14 بمصادر بيانات سهول الفعليّة. العمود «الجاهزيّة»:
✅ مصدر حقيقيّ جاهز · 🟡 موجود جزئيّاً/يحتاج ربطاً · ⛔ فجوة موثّقة.

| # | شاشة النموذج | المقابل في سهول | الهوك/الـAPI الحقيقيّ | الجاهزيّة |
|---|---|---|---|---|
| 1 | **Auth** | `LoginPage`/`SignupPage` | `useAuthStore` · `POST /api/v1/auth/*` | ✅ |
| 2 | **Dashboard** | `DashboardPage` / إثبات `FieldAppPreview` | `useDashboardData` · `useWeatherForecast` · `useAlerts` | ✅ |
| 3 | **Fields** | `FieldManagementPage` | `useFields` (`GET /api/v1/fields`) | ✅ |
| 4 | **Field Map** | `FieldIndicatorMap` / `SpatialIndicatorsPage` | `useIndicatorGrid` · raster-service (NDVI حقيقيّ، #152) | ✅ |
| 5 | **Field Detail** (تبويبات) | `FieldDetailPanel` | `useFieldDetail` (`GET …/fields/{id}`) | ✅ |
| 5a | ↳ Summary | — | `useFieldDetail` + `useFieldRecommendations` | ✅ |
| 5b | ↳ Field Data | — | `useFieldDetail` (محصول/مساحة/موسم) | ✅ |
| 5c | ↳ Sensor Data | `DevicesPage` | `useDevices` · `useDeviceTelemetry` · `useFieldSoilMoisture` | ✅ |
| 5d | ↳ Agronomy | `RecommendationPage` | `useFieldRecommendations` · `useSoilNRecommendation` | ✅ |
| 5e | ↳ Weather | `WeatherAdvicePage` | `useWeatherForecast` (يشمل شمس/شروق/غروب/إشعاع #159) | ✅ |
| 5f | ↳ Agenda | `TasksPage`/`ActivitiesPage` | `useTasks` · `useActivities` | ✅ |
| 5g | ↳ Settings | `SettingsPage` | `useUpdateField` · `useNotificationPreferences` | ✅ |
| 6 | **Field Health** | جزء من `SatellitePage` | `useFieldTimeseries` · `useCurrentNDVI` · `useDiseaseRisk` | ✅ |
| 7 | **Yield Analysis** | `AnalyticsPage` | `useSimulateSeason` (WOFOST) · `useSeasons` | ✅ |
| 8 | **Reports** | `ReportsPage` | `useFieldReport` · `useSeasonReport` | 🟡 (PDF مؤجَّل — المجال 11) |
| 9 | **VRA** (وصفة متغيّرة) | جزء من `SpatialIndicatorsPage` | `useFieldPrescription` (`…/fields/{id}/prescription`) | ✅ |
| 10 | **Add Task** | `TasksPage` (إنشاء) | `useCreateActivity` (idempotent، #157) · `useTasks` | ✅ |
| 11 | **Sensors** | `DevicesPage` | `useDevices` · `useRegisterDevice` · `useValves` | ✅ |
| 12 | **More** (قائمة) | `Sidebar`/`NAV` | تنقّل محلّيّ (لا API) | ✅ |
| 13 | **Machine Data** | `EquipmentPage` | `useEquipment` · `useMaintenance` · `useLogMaintenance` | ✅ |
| 14 | **Subscription** | — | ⛔ لا نقطة اشتراك في الواجهة بعد (ERPNext هو الـERP) | ⛔ |

### إضافات سهول تتجاوز النموذج (قوّة محلّيّة)
- **التقويم النجميّ/الأنواء:** `GET /api/v1/calendars/today` (#160) — منزلة قمريّة +
  نوء + شهر حِميَريّ + نافذة زراعة. وسمٌ صادق `display_only` (خارج محرّك القرار).
  يُقترَح كـ**بطاقة في Dashboard** (`Card` + `Pill`).
- **المؤشّرات الـ15 + المشتقّات البكسليّة:** `GET /api/v1/indicators/catalog` —
  تغذّي تبويب Field Health و«المؤشّرات المكانيّة».
- **المايسترو/التصعيد:** `FieldIntelligencePage` + `PestEscalationPage` (AI↔بشريّ).

---

## 5) فجوات موثّقة (تحتاج قراراً قبل الكسوة)

| الفجوة | الشاشة المتأثّرة | الحالة الحاليّة | القرار المطلوب |
|---|---|---|---|
| تشخيص المرض بالصورة | Field Health (كاميرا) | `edge-inference` جاهز، النموذج غير مُموَّن ⇒ 503 صادق | تمويل/تدريب نموذج ONNX |
| اشتراكات | Subscription | لا واجهة | ربط ERPNext أو إخفاء الشاشة |
| تقارير PDF | Reports | بيانات جاهزة، لا تصدير PDF | اعتماد مولّد PDF (المجال 11) |
| إحداثيّات الآبار/العيّنات/الحسّاسات على الخريطة | Sensors/Irrigation/Soil | جداول بلا طبقة مكانيّة كاملة | طبقة GIS (المجالات 5/6/9/10، P1) |
| المعرفة المجتمعيّة داخل المنصّة | (لا مقابل) | Telegram + RAG فقط | ميزة شات/مجتمع داخليّة (المجال 13) |

---

## 6) خطّة الكسوة التدريجيّة (عند اعتماد المواصفة)

1. **Dashboard** أوّلاً (أعلى قيمة، يستهلك معظم الذرّات) — مُنجَز كإثبات في PR #161.
2. **Field Detail** (التبويبات السبعة) — يربط أكبر سطح بيانات حقيقيّ.
3. **Fields + Field Map** — قائمة + NDVI مكانيّ حقيقيّ.
4. الباقي حسب الأولويّة، مع إغلاق الفجوات أعلاه أوّلاً بأوّل.

> كلّ خطوة: فرع → `tsc --noEmit` + `vite build` → PR → مراجعة Copilot → لقطة المستخدم
> للتلميع البصريّ (لا يمكن التحقّق البصريّ آليّاً).

# مواصفة التصميم الموحّدة لسهول (SAHOOL Unified UX) — دمج أفضل الخصائص

> **الحالة:** مواصفة مرجعيّة (Design Spec) — **دمجٌ** لا استبدال.
> **الغاية:** صهر أفضل ما في **FieldView** (الزراعة/المحصول/المؤشّرات) و**John
> Deere Operations Center** (الأسطول/المعدّات/التتبّع اللحظيّ) — وغيرهما — في
> **نظام تصميم سهوليّ واحد**، مع **وحدات جديدة جامعة** تستوعب المسارين، وربطٍ بـ
> **APIs سهول الحقيقيّة**. لا كود سلوكيّ هنا.
> **يبني على:** `UI_DESIGN_SPEC_FIELDAPP.md` (#162) ويوسّعه ليكون المرجع الأشمل.
> **مبدأ الهويّة والملكيّة:** نقتبس **الأنماط وطرق العرض** لا **العلامات
> التجاريّة**. ألوان سهول الموحّدة هويّتها الخاصّة (ليست أخضر/أصفر JD ولا
> بنّيّ/ذهبيّ FieldView حرفيّاً)، وكلّ الهيوات قابلة للضبط من لقطات المستخدم.

---

## 0) فلسفة الدمج

| من FieldView نأخذ | من John Deere نأخذ | يبقى سهوليّاً أصيلاً |
|---|---|---|
| تركيز المحصول/الحقل | تركيز الأسطول/المعدّة اللحظيّ | الأنواء/التقويم النجميّ (#160) |
| منحدر NDVI + صحّة النبات | عدّادات نصف-قطريّة (وقود/DEF/ساعات) | المايسترو/التصعيد (AI↔بشريّ) |
| تبويبات تفصيل الحقل | بطاقات مراقبة قابلة للطيّ | كتالوج الـ15 مؤشّراً + المشتقّات البكسليّة |
| الوصفة المتغيّرة VRA | معالج «خطّة عمل ← إرسال للكابينة» | محرّك القرار الزراعيّ (WOFOST) |
| تحليل الإنتاجيّة | مقارنة طبقات جنباً لجنب + Colormap | الريّ التشغيليّ + المحابس |

**القاعدة الذهبيّة:** *خريطة واحدة كثيرة الطبقات، تقويم موحّد، وتنبيهات موحّدة* —
بدل تطبيقين منفصلين (زراعة/أسطول) نصهرهما في «مركز عمليّات» واحد.

---

## 1) معماريّة المعلومات الموحّدة (IA)

> ✅ مُجسَّدة في `sections/UnifiedCabin.tsx` — قشرة تطبيق واحدة بشريط
> `BottomTabBar` سفليّ تستضيف شاشات الدمج. الوجهات الموصولة: **القيادة**
> (`OperationCommand`) · **الخريطة** (`FieldMapCenter`) · **التخطيط** (مبدّل علويّ
> يجمع **توصية←تنفيذ** `RecommendationFlow` + **المهام** `FieldTasksCabin`) ·
> **المراقبة** (`HybridMonitor`) · **التحليل** (`AnalyzeCabin`). وجهة **الإعداد**
> تُظهر بطاقة «قيد الإنشاء» صريحة وتشير للقسم الكلاسيكيّ — ووحدتها الموحّدة **قيد
> التنفيذ في فرع منفصل** (لم تُدمَج بعد). مسجّلة في `App.tsx` بمفتاح `unified-cabin`.

شريط سفليّ من **6 وجهات رئيسيّة**، كلٌّ منها يبتلع ما يقابله في النموذجين:

| # | الوجهة (Tab) | تبتلع من FieldView | تبتلع من JD | مصدر سهول |
|---|---|---|---|---|
| 1 | **القيادة** (Command/Home) | Dashboard | Home/Overview | `useDashboardData` · `useAlerts` |
| 2 | **الخريطة** (Map) | FieldMap/NDVI/VRA المكانيّة | Machine markers + Radar + Boundaries | `useIndicatorGrid` · `useFields` · (طبقة GIS ⛔) |
| 3 | **التخطيط** (Plan) | AddTask + التوصيات | Work Planner → Send to Cab | `useFieldRecommendations` · `useCreateActivity` · `useTasks` |
| 4 | **المراقبة** (Monitor) | SensorData | Daily Summary/Fleet telemetry | `useDevices` · `useDeviceTelemetry` · (DTC/وقود ⛔) |
| 5 | **التحليل** (Analyze) | YieldAnalysis/Health/Reports | Field Analyzer + Side-by-Side | `useSimulateSeason` · `useFieldTimeseries` · `useFieldReport` |
| 6 | **الإعداد** (Setup) | Settings/Subscription | Land/Equipment/Team/Products/Org | `useUpdateField` · `useEquipment` · إلخ |

**فائض «المزيد» (More overflow)** — وحدات سهول الأصيلة التي لا مقابل لها في
النموذجين: الريّ التشغيليّ · الأنواء/التقويم · المايسترو · تصعيد الآفة · الحوكمة ·
المستشار الذكيّ (RAG).

---

## 2) الوحدات الجديدة الجامعة (New Unifying Modules)

وحداتٌ تُولَد من **الدمج** نفسه — لا توجد في أيّ نموذج منفرد:

| الوحدة الجديدة | تصهر | القيمة | الحالة |
|---|---|---|---|
| **مركز العمليّات الموحّد** (Operation Command) | Dashboard (FV) + Home (JD) | كابينة واحدة: صحّة الحقول + حالة المعدّات + التنبيهات + عمل اليوم. | ✅ مُنجَز |
| **الخريطة متعدّدة الطبقات** (One Map · Many Layers) | NDVI/VRA (FV) + machines/radar/boundaries (JD) + آبار/حسّاسات (سهول) | كلّ شيء على خريطة واحدة بمبدّل طبقات؛ نهاية تشتّت الخرائط. | ✅ مُنجَز |
| **مخطّط من التوصية للتنفيذ** (Recommendation→Execution) | التوصية الزراعيّة (FV) + معالج خطّة العمل/الإرسال (JD) | توصية المحرّك تتحوّل بنقرة إلى خطّة عمل مُسنَدة لمعدّة/عامل/خطوط توجيه. | ✅ مُنجَز (`sections/RecommendationFlow.tsx`) |
| **المراقبة الهجينة** (Hybrid Monitor) | حسّاسات التربة/الريّ (FV/سهول) + تتبّع الآلة اللحظيّ (JD) | لوحٌ واحد يجمع قراءات الحقل وعدّادات الآلة. | ✅ مُنجَز (`sections/HybridMonitor.tsx`) |
| **التحليل** (Analyze Cabin) | YieldAnalysis/Health/Reports (FV) + Field Analyzer (JD) | لوحٌ واحد: سلسلة المؤشّر الزمنيّة + مخاطر الأمراض + الإنتاج المُقدَّر. | ✅ مُنجَز (`sections/AnalyzeCabin.tsx`) — الأحدث |
| **مفكّرة العمليّات الموسميّة** (Seasonal Agenda) | Agenda (FV) + Work History (JD) + الأنواء (سهول) | جدول زمنيّ يدمج المهام والعمليّات والنوافذ الفلكيّة. | 🟡 جزئيّ (كابينة المهام `sections/FieldTasksCabin.tsx`) |

---

## 3) نظام التصميم الموحّد (Unified Design System)

### 3.1 الرموز (Tokens) — هويّة سهول الموحّدة
> ✅ مُنجَز: `frontend/src/components/ds/tokens.ts` (هويّة + منحدر NDVI + منحدرات
> CMAP + `resourceColor`/`severityTone`). الهيوات قابلة للضبط من لقطات المستخدم.

| المجموعة | الرمز | القيمة المقترحة | الدور | المصدر الملهِم |
|---|---|---|---|---|
| **الأساس** | `green` | `#2E7D32` | الأساس الزراعيّ/الهويّة | سهول الحاليّ |
| | `greenDark` | `#1B5E20` | رؤوس داكنة | JD greenDark |
| **الإجراء** | `accent` | `#E8A020` | CTA/تمييز/تبويب نشط | دمج ذهب FV + أصفر JD (مضبوط) |
| **التربة** | `earth` / `earthSoft` | `#5B4636` / `#FBF7F0` | نصّ ثانويّ / خلفيّة دافئة | FieldView |
| **الحالات** | `ok/warn/danger/info` | `#3EB050`/`#E8A020`/`#C0392B`/`#1A6FBD` | نغمات صادقة | مشترك |
| **NDVI** | `ndvi1..6` | منحدر الستّ درجات | المؤشّرات المكانيّة | FieldView (#162) |
| **Colormap** | `cmap.{yield,soil,ndvi,elevation,ec}` | منحدرات 6-درجات | طبقات التحليل | JD Analyze |

### 3.2 جرد المكوّنات الموحّد
> ✅ **كلّ المكوّنات العشرين مُنجَزة ومُختبَرة بناءً/أنواعاً** (`ds/atoms.tsx` +
> `ds/merge.tsx`، وفيها ذرّة `Button` موحّدة). أُضيفت كذلك وحدات مشتركة جامعة
> تُلغي التكرار عبر الشاشات: قشرة الكابينة `ds/cabin.tsx` (`FieldCabin`)،
> تسميات/نغمات الحالات `ds/status.ts`، ومساعِدات `lib/geo.ts` + `lib/dates.ts`
> (`geomToPolygon`/`fmtDateAr`/خرائط الحالة). كما وُحِّد تطبيع خيارات الحقل في
> `lib/fields.ts` (`toFieldOption` — مصدر واحد للحقيقة) عبر الهوك `hooks/useFieldOptions.ts`
> الذي تستهلكه شاشات الدمج بدل إعادة كتابة تحويل الحقل في كلّ شاشة.

**موروثة من #161 (FieldView):** `Card · SectionLabel · Pill · Badge · StatBox ·
ProgressBar · Row · TabBar · FAB · BottomSheet`. ✅

**مقتبسة من John Deere (جديدة):** ✅ (العشرة جميعها مُجسّدة)
| المكوّن | الخصائص | الدور | الأصل |
|---|---|---|---|
| `RadialGauge` | `pct, size?, color?, label?` | عدّاد نصف-قطريّ (وقود/DEF/إنجاز) | JD FuelGauge |
| `ExpandableCard` | `header, children, expanded, onToggle` | بطاقة مراقبة قابلة للطيّ | JD Monitor |
| `StatGrid` | `items[{val,label,unit,color,icon}]` | شبكة إحصاءات سريعة | JD Overview |
| `AlertChip` | `type(danger/warn/dtc/info/ok), label` | شريحة تنبيه ملوّنة | JD |
| `Stepper` | `steps[], active, onStep` | معالج متعدّد الخطوات | JD Work Planner |
| `LayerSwitcher` | `layers[], active, onChange` | مبدّل طبقات الخريطة/التحليل | JD Map/Analyze |
| `ColormapLegend` | `colors[], lowLabel, highLabel, title` | مفتاح ألوان الطبقة | JD Analyze |
| `MachineMarker` | `icon, status, alert?, speed?, onClick` | مؤشّر آلة على الخريطة (مع نبض الحالة) | JD Map |
| `SideBySide` | `left, right, layers` | مقارنة طبقتين جنباً لجنب | JD Analyze |
| `BottomTabBar` | `tabs[6], active, onChange` | شريط الوجهات الستّ | JD |

### 3.3 أنماط العرض المقتبَسة (Presentation Patterns / الاقتباسات)
- **عدّادات نصف-قطريّة** للموارد (وقود/DEF/بطّاريّة/رطوبة) — أوضح من الأشرطة.
- **بطاقة مراقبة تتوسّع** لتكشف التفاصيل عند الطلب (تقليل الازدحام).
- **خريطة واحدة + مبدّل طبقات** بدل شاشات منفصلة لكلّ مؤشّر.
- **مقارنة جنباً لجنب + Colormap Legend** للتحليل المكانيّ (إنتاجيّة/تربة/NDVI).
- **معالج خطوات** للعمليّات المركّبة (اختر حقلاً ← العمليّة ← الإسناد ← الإرسال).
- **شرائح تنبيه مصنّفة** (حرِج/تحذير/عطل DTC/معلومة) بأيقونة ولون موحّدين.
- **مؤشّرات آلة نابضة** بحالة لونيّة + شارة إنذار عند نقص حرج.
- **شريط وجهات سفليّ ثابت** (موبايل أوّلاً) — تنقّل بإبهام واحد، RTL.

---

## 4) خريطة الشاشات الموحّدة ← API سهول الحقيقيّ

دمج شاشات النموذجين تحت الوجهات الستّ. الجاهزيّة: ✅ جاهز · 🟡 جزئيّ · ⛔ فجوة.

| الوجهة | الشاشة الموحّدة | الهوك/الـAPI الحقيقيّ | جاهزيّة |
|---|---|---|---|
| القيادة | مركز العمليّات | `useDashboardData` · `useAlerts` · `useWeatherForecast` | ✅ |
| القيادة | بطاقة الأنواء | `GET /api/v1/calendars/today` (#160) | ✅ |
| الخريطة | NDVI/مؤشّرات مكانيّة | `useIndicatorGrid` · raster-service (#152) · مبدّل الطبقات من الكتالوج (`renderable`) | ✅ |
| الخريطة | وصفة VRA | `useFieldPrescription` | ✅ |
| الخريطة | مواقع المعدّات اللحظيّة | telematics GPS | ⛔ (لا طبقة GPS للآلات) |
| الخريطة | رادار/أمطار | `useWeatherForecast` + بلاطات رادار | 🟡 (طقس ✅، بلاطات رادار ⛔) |
| التخطيط | توصيات ← خطّة عمل | `useFieldRecommendations` · `useCreateActivity` (#157) | ✅ |
| التخطيط | إرسال للكابينة (ISOBUS) | task→display push | ⛔ |
| التخطيط | خطوط التوجيه (AB Lines) | guidance lines | ⛔ |
| المراقبة | حسّاسات التربة/الريّ | `useDevices` · `useDeviceTelemetry` | ✅ |
| المراقبة | عدّادات الآلة (وقود/DEF/ساعات) | machine telemetry | 🟡 (إطار الأجهزة ✅، حقول الآلة المخصّصة ⛔) |
| المراقبة | أكواد الأعطال DTC | fault codes feed | ⛔ |
| التحليل | الإنتاجيّة/المحاكاة | `useSimulateSeason` (WOFOST) · `useSeasons` | ✅ |
| التحليل | السلاسل الزمنيّة/الصحّة | `useFieldTimeseries` · `useDiseaseRisk` | ✅ |
| التحليل | التقارير | `useFieldReport` · `useSeasonReport` | 🟡 (PDF مؤجَّل) |
| الإعداد | الحقول/الحدود | `useFields` · `useUpdateField` | ✅ |
| الإعداد | المعدّات والصيانة | `useEquipment` · `useMaintenance` · `useLogMaintenance` | ✅ |
| الإعداد | الفريق/الشركاء | RBAC (`permissions.ts`) · `useUsers` | 🟡 |
| الإعداد | الاشتراك | ERPNext | ⛔ |
| المزيد | الريّ التشغيليّ/المحابس | `useValves` · `useIrrigationOps` | ✅ |
| المزيد | المايسترو/تصعيد الآفة | `FieldIntelligence` · `PestEscalation` | ✅ |
| المزيد | المستشار الذكيّ | `ChatbotPage` (RAG) | ✅ |

> **مبدّلات الطبقات مدفوعة بالكتالوج (مصدر حقيقة واحد):** أضافت الخلفيّة عَلَم
> `renderable` إلى `GET /api/v1/indicators/catalog`؛ و`SatellitePage` +
> `SpatialIndicatorsPage` تشتقّان مبدّل طبقات الخريطة من عناصر `renderable=true`
> فقط (لا قائمة مُبرمَجة) — فلا طبقة ميتة ولا مفقودة. أُزيلت كذلك تبعيّة
> `maplibre-gl` الميتة، ووُصلت طبقة `msi` (الإجهاد المائي) ضمن الطبقات القابلة للرسم.

---

## 5) الفجوات التي يكشفها الدمج (قرارات قبل الكسوة)

| الفجوة | مصدرها | الحالة | القرار المطلوب |
|---|---|---|---|
| طبقة GPS لمواقع الآلات | JD Map | لا telematics مكانيّ | تكامل telematics/ISOBUS أو إخفاء الطبقة |
| عدّادات وقود/DEF/ساعات لكلّ آلة | JD Monitor | إطار الأجهزة عامّ | مخطّط telemetry للمعدّات |
| أكواد الأعطال DTC | JD | لا تغذية أعطال | مصدر CAN/J1939 أو إخفاء |
| إرسال للكابينة (Send to Cab) | JD Plan | لا دفع للشاشة | تكامل ISOBUS/display |
| خطوط التوجيه AB | JD Plan | لا توجيه | خارج النطاق الحاليّ |
| بلاطات الرادار | JD Map | طقس ✅ بلا بلاطات | مزوّد بلاطات رادار |
| تشخيص المرض بالصورة | FieldView | نموذج غير مُموَّن (503 صادق) | تمويل ONNX |
| تقارير PDF | FieldView | بيانات ✅ بلا تصدير | مولّد PDF (المجال 11) |
| الاشتراكات | JD/FV | لا واجهة | ربط ERPNext |

> **صدق:** الفجوات ⛔ تظهر في الواجهة كحالات «غير متاح» صريحة (لا تلفيق
> عدّادات أو مواقع وهميّة) — يطابق مبدأ «لا بيانات وهميّة».

---

## 6) خطّة الكسوة التدريجيّة

1. ✅ **توحيد نظام التصميم** — استُكمل `ds/` بالمكوّنات المقتبسة العشرة
   (RadialGauge، ExpandableCard، LayerSwitcher، SideBySide…). بناء/أنواع خضراء.
2. ✅ **مركز العمليّات الموحّد** (القيادة) — مُنجَز (`sections/OperationCommand.tsx`).
3. ✅ **الخريطة متعدّدة الطبقات** — مُنجَز (`sections/FieldMapCenter.tsx`).
   وأُنجزت أيضاً **كابينة المهام** (`sections/FieldTasksCabin.tsx`) كأوّل تجسيد
   لـ«مفكّرة العمليّات الموسميّة» (Stepper + BottomTabBar).
4. ✅ **التخطيط (توصية←تنفيذ)** (`sections/RecommendationFlow.tsx`) ثمّ **المراقبة
   الهجينة** (`sections/HybridMonitor.tsx`) ثمّ **التحليل** (`sections/AnalyzeCabin.tsx`)
   — كلّها مُنجَزة. وضُمّت الوجهات الخمس في قشرة موحّدة `sections/UnifiedCabin.tsx`
   (`BottomTabBar`). وجهة **الإعداد** الموحّدة **قيد التنفيذ في فرع منفصل**.
5. ◻️ إغلاق فجوات ⛔ أوّلاً بأوّل حسب الأولويّة (الطبقة المكانيّة P1).

> راجع **§8 حالة التنفيذ** لتفصيل ما بُني فعليّاً (الملفّات + المكوّنات المستهلَكة
> + الهوكات الحقيقيّة + ملاحظات الصدق).
>
> كلّ خطوة: فرع → `tsc --noEmit` + `vite build` → PR → مراجعة Copilot → لقطة
> المستخدم للتلميع البصريّ (لا يمكن التحقّق البصريّ آليّاً).

---

## 7) مرجع النماذج الملهِمة
- **FieldView clone** — مصدر المسار الزراعيّ (14 شاشة، رموز بنّيّ/ذهبيّ، NDVI).
- **John Deere Operations Center clone** — مصدر المسار الأسطوليّ (10 شاشات:
  Login/Home/Map/Plan/Monitor/Analyze/Setup/Maintenance/Alerts/EquipmentDetail؛
  رموز أخضر/أصفر؛ عدّادات/معالج/مقارنة طبقات).
- **سهول الأصيل** — الأنواء، الـ15 مؤشّراً، WOFOST، المايسترو، الريّ، RBAC.

---

## 8) حالة التنفيذ — مُحقَّق (مدموج في `main`)

**ستّ** شاشات دمج موصولة ببيانات سهول الحقيقيّة (قراءة فقط · معاينة)، تستهلك كامل
مكوّنات `ds/`، مجموعةً تحت قشرة تطبيق واحدة. كلّها مربوطة في `App.tsx` (شارة «دمج»)
و`permissions.ts`. الوجهات الخمس الجاهزة محمولة داخل `UnifiedCabin` بشريط
`BottomTabBar`، ووجهة **الإعداد** تُظهر «قيد الإنشاء» (وحدتها الموحّدة **قيد التنفيذ
في فرع منفصل** — لم تُدمَج).

| الشاشة (الوحدة) | الملفّ | المكوّنات المستهلَكة | الهوكات الحقيقيّة |
|---|---|---|---|
| القشرة الموحّدة | `sections/UnifiedCabin.tsx` | BottomTabBar · TabBar · FieldCabin · Card | يستضيف الشاشات أدناه (lazy) ويبدّل بينها؛ الإعداد «قيد الإنشاء» |
| مركز العمليّات | `sections/OperationCommand.tsx` | StatGrid · RadialGauge · AlertChip · ExpandableCard · FieldCabin | `useFields` · `useEquipment` · `useDevices` · `useAlerts` · `useTasks` · `useWeatherForecast` |
| مركز الخرائط | `sections/FieldMapCenter.tsx` | LayerSwitcher · ColormapLegend · SideBySide · MachineMarker · FieldCabin | `useFields` · `useDevices` + `FieldIndicatorMap` (بلاطات raster الحقيقيّة) |
| توصية ← تنفيذ | `sections/RecommendationFlow.tsx` | Stepper · StatGrid · AlertChip · FieldCabin | `useFieldRecommendations` · `useCreateActivity` · `useTasks` |
| المراقبة الهجينة | `sections/HybridMonitor.tsx` | ExpandableCard · RadialGauge · StatGrid · AlertChip · FieldCabin | `useDevices` · `useDeviceTelemetry` |
| كابينة المهام | `sections/FieldTasksCabin.tsx` | Stepper · BottomTabBar · StatGrid · FieldCabin | `useTasks` |
| التحليل | `sections/AnalyzeCabin.tsx` | RadialGauge · StatGrid · FieldCabin · `severityTone` | `useFieldTimeseries` · `useVegetationTimeseries` · `useDiseaseRisk` · `useSeasons` |

**التغطية:** كلّ مكوّنات الدمج العشرة مُستهلَكة عبر الشاشات
(StatGrid/RadialGauge/AlertChip/ExpandableCard → العمليّات/المراقبة/التحليل؛
LayerSwitcher/ColormapLegend/SideBySide/MachineMarker → الخرائط؛
Stepper/BottomTabBar → المهام/التوصية والقشرة). وتشترك الشاشات في وحدات `ds/`
الجامعة (`FieldCabin` من `ds/cabin.tsx`، تسميات/نغمات `ds/status.ts`، ذرّة
`Button` في `ds/atoms.tsx`) ومساعِدات `lib/geo.ts`/`lib/dates.ts`/`lib/fields.ts`
(`toFieldOption`) عبر الهوك `hooks/useFieldOptions.ts` — مصدر واحد للحقيقة بدل
التكرار في كلّ شاشة.

**مبدّلات الطبقات مدفوعة بالكتالوج:** مبدّل طبقات الخريطة في `SatellitePage`
و`SpatialIndicatorsPage` يُشتقّ من `GET /api/v1/indicators/catalog` (عناصر
`renderable=true` فقط) لا من قائمة مُبرمَجة — مصدر حقيقة واحد فلا طبقة ميتة ولا
مفقودة. أُزيلت كذلك تبعيّة `maplibre-gl` الميتة، ووُصلت طبقة `msi` (الإجهاد المائي)
ضمن الطبقات القابلة للرسم.

**الصدق (مطبَّق فعليّاً، لا ادّعاء):**
- كلّ نسبة مشتقّة من قيمة حقيقيّة (متوسّط NDVI، نسبة الاتّصال، نسبة الإنجاز،
  موضع `Stepper` من حالة المهمّة، سلسلة التحليل من متوسّطات COG الحقيقيّة). لا قيم
  مُلفّقة — الغائب يُعرَض «—» (مثلاً حقول المحاكاة `sim_*` قبل تشغيلها).
- **لا عدّادات وقود/DEF** ولا **مواقع آلات** على الخريطة (فجوتان ⛔ موثّقتان في
  §5) — الأجهزة تظهر كمؤشّرات حالة منسوبة للحقل لا كإحداثيّات مزعومة.
- حالات تحميل/فراغ/خطأ/«بلا-هندسة»/«وجهة-فارغة» صريحة في كلّ شاشة.

**الجودة:** `tsc --noEmit` نظيف · `vite build` ناجح · CI كامل أخضر · بلا أحرف
اتّجاهيّة · عُولجت ملاحظات مراجعة الكود (شكل بيانات المهام، تسجيل الصفحات في
`permissions.ts`، تفادي إعادة بناء خريطة Leaflet عند تبديل الطبقة).

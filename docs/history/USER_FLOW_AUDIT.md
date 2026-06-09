# مراجعة تدفّق دخول المستخدم — مقارنة سهول × FieldView

> **الغرض:** تشخيص الحالة الحاليّة لتدفّق دخول المستخدم في موبايل سهول،
> مقارنته بنمط Climate FieldView، تحديد الفجوات، واقتراح تدفّق محسَّن
> يتناسب مع السياق اليمني (offline-first, RTL, low digital literacy).

---

## ١. الحالة الحاليّة في سهول (الواقع)

```
[App Launch]
   ↓
[AuthProvider checks token]
   ↓
   ├─ token? → me() → user set → Tabs (Dashboard فاضي)
   └─ no token → LoginScreen
           ↓
       [user_id + tenant_id + name + role]
           ↓
       apiLogin → Tabs (Dashboard فاضي)
```

### المشاكل الفعليّة

| # | المشكلة | الأثر على المزارع اليمني |
|---|---------|---------------------------|
| ١ | لا تمييز بين user جديد ومستخدم عائد | المستخدم الجديد يصل لـDashboard فارغ ولا يعرف ماذا يفعل |
| ٢ | LoginScreen يطلب `tenant_id` و `user_id` | غير مفهوم — منطق backend مكشوف للمزارع |
| ٣ | لا onboarding sequence | لا فهم لقيمة المنصّة قبل الالتزام |
| ٤ | Dashboard فارغ بلا حقول = شاشة بيضاء | الـempty state أسوأ تجربة في mobile UX |
| ٥ | لا "إضافة حقلك الأوّل" guided | المستخدم يبحث عن زرّ مخفي في tabs |
| ٦ | Permission requests غير مفهومة (location, camera) | iOS/Android يرفضها لو لم تُطلَب في سياق |
| ٧ | لا "Skip" أو "Tour" للمتقدّمين | الـpower users يتأذّون لو وُضع tutorial إجباري |
| ٨ | لا حفظ "آخر شاشة" للعودة | المستخدم يضيع بعد إعادة فتح التطبيق |

---

## ٢. نمط Climate FieldView (المرجع)

### المراحل العشر الكاملة

```
١. Splash Screen + version check
       ↓
٢. Welcome (٣ شرائح value-prop)
       ↓
٣. Auth gate (Login | Create account)
       ↓
٤. [إن جديد] Account setup wizard
       ├─ الاسم + البلد
       ├─ المحاصيل المهتمّ بها
       └─ نظام الوحدات (US/Metric)
       ↓
٥. Permission requests (في سياق)
       ├─ Location → "لإيجاد حقولك"
       └─ Notifications → "للتنبيهات الزراعية"
       ↓
٦. First-field guided drawing
       ├─ "ارسم حقلك الأوّل"
       ├─ tutorial overlay
       └─ Sample crop card prefilled
       ↓
٧. Sync settings explicit
       └─ "هذا التطبيق يعمل offline"
       ↓
٨. Optional tour (٤-٥ tips قابلة للـSkip)
       ↓
٩. Main Dashboard (مع بيانات الحقل الجديد)
       ↓
١٠. [Returning] Resume last screen
```

### القيم الجوهريّة من FieldView

```
✓ التدرّج: لا شيء إلزامي إلّا الأساسي
✓ الجدوى: كل خطوة لها سبب واضح للمستخدم
✓ الإنجاز: المستخدم يخرج بـ"حقل واحد على الأقلّ" بعد ٥ دقائق
✓ الذاكرة: العودة تتذكّر آخر مكان
```

---

## ٣. التدفّق المقترَح لسهول (مكيَّف للسياق اليمني)

```
[App Launch]
       ↓
[Splash 1.5 ثانية + Brand]
       ↓
[Check stored state]
       ├─ has user + completed_onboarding? → Resume last route
       ├─ has user + not completed_onboarding? → Continue onboarding from saved step
       └─ no user → WelcomeFlow
```

### تفصيل التدفّق

```
╔════════════════════════════════════════════════════════╗
║ A. Welcome Flow (للمستخدم الجديد)                       ║
╠════════════════════════════════════════════════════════╣
║                                                         ║
║  A1. WelcomeScreen                                      ║
║      ٣ شرائح horizontal swipe:                          ║
║      [١] "خرائط ذكيّة لحقولك"                          ║
║          - رسم بـpolygon أو pivot                       ║
║      [٢] "صور أقمار صناعيّة مجانيّة"                    ║
║          - حالة المحصول من Sentinel-2                   ║
║      [٣] "يعمل بدون إنترنت"                            ║
║          - مهمّ في الريف اليمني                         ║
║      ↓                                                  ║
║      [زرّ: ابدأ مجاناً] [رابط: عندي حساب]              ║
║                                                         ║
║  A2. AccountSetupScreen (٣ خطوات)                       ║
║      Step 1/3: من أنت؟                                  ║
║       - الاسم: ______                                   ║
║       - دور: مزارع | مهندس | مدير                      ║
║       - رقم الجوّال (اختياري): ______                  ║
║      Step 2/3: أين أنت؟                                 ║
║       - المحافظة: [قائمة منسدلة]                       ║
║       - المديريّة: [نصّ حرّ]                          ║
║      Step 3/3: ماذا تزرع؟                              ║
║       - [☐ قمح] [☐ شعير] [☐ سمسم] [☐ ذرة]              ║
║       - [☐ خضار] [☐ فاكهة] [☐ بقوليّات]                 ║
║       - [☐ أخرى: _____]                                ║
║      ↓                                                  ║
║      [إنشاء الحساب]                                    ║
║                                                         ║
║  A3. PermissionPrimerScreen                             ║
║      "نحتاج إذنك لاستخدام:"                            ║
║      [📍 الموقع] - "لإيجاد حقولك على الخريطة"          ║
║      [📷 الكاميرا] - "لتصوير المحصول والمشاكل"         ║
║      [🔔 الإشعارات] - "لتذكيرك بمواعيد الري والحصاد"    ║
║      ↓                                                  ║
║      [زرّ: متابعة] [رابط: لاحقاً]                       ║
║      → استدعاء system permissions الفعلي                ║
║                                                         ║
║  A4. FirstFieldDecisionScreen                           ║
║      "هل تريد إضافة حقلك الأوّل الآن؟"                  ║
║      [نعم، أضف حقلي] → FieldDrawingScreen (مع tour)     ║
║      [لاحقاً] → Dashboard                              ║
║                                                         ║
║  A5. CompletionScreen                                   ║
║      "🌾 جاهز! إليك ملخّص ما أنشأت..."                  ║
║      - حقل: __________ (المساحة)                       ║
║      - المحصول: ______                                  ║
║      [زرّ: ابدأ الاستخدام] → Dashboard                  ║
║                                                         ║
╚════════════════════════════════════════════════════════╝

╔════════════════════════════════════════════════════════╗
║ B. Login Flow (للمستخدم العائد)                         ║
╠════════════════════════════════════════════════════════╣
║                                                         ║
║  B1. LoginScreen (مُحسَّن)                              ║
║       - رقم الجوّال OR اسم المستخدم                     ║
║       - كلمة المرور                                     ║
║       - [☐ تذكّرني] (default ✓)                        ║
║       ↓                                                  ║
║       [دخول] → Resume last route OR Dashboard           ║
║                                                         ║
║  B2. لا tenant_id/user_id مكشوف للمستخدم!              ║
║       backend يولّدها، UI لا يطلبها                     ║
║                                                         ║
╚════════════════════════════════════════════════════════╝

╔════════════════════════════════════════════════════════╗
║ C. Empty Dashboard Handling                             ║
╠════════════════════════════════════════════════════════╣
║                                                         ║
║  C1. لو لا حقول:                                       ║
║       لا تعرض dashboard فارغ.                          ║
║       اعرض EmptyStateCard:                              ║
║                                                         ║
║       ┌─────────────────────────────────┐              ║
║       │  🌾 ابدأ بإضافة حقلك الأوّل      │              ║
║       │                                  │              ║
║       │  لتظهر هنا:                      │              ║
║       │  • صور الأقمار الصناعيّة         │              ║
║       │  • حالة المحصول                  │              ║
║       │  • توصيات الري                   │              ║
║       │                                  │              ║
║       │  [+ إضافة حقل]                  │              ║
║       └─────────────────────────────────┘              ║
║                                                         ║
╚════════════════════════════════════════════════════════╝
```

---

## ٤. ما يجب بناؤه (خارطة الـimplementation)

### الأولويّة ١ (الأساسي — يحلّ ٨٠٪ من المشاكل)

```
┌─ src/screens/onboarding/
│  ├─ WelcomeScreen.tsx           (٣ شرائح value-prop)
│  ├─ AccountSetupScreen.tsx      (٣ خطوات wizard)
│  ├─ PermissionPrimerScreen.tsx  (طلب الأذونات في سياق)
│  └─ CompletionScreen.tsx        (احتفال + ملخّص)
│
├─ src/state/
│  └─ onboardingState.ts          (تتبّع التقدّم + persist)
│
├─ src/components/
│  └─ EmptyStateCard.tsx          (للـdashboard الفارغ)
│
└─ App.tsx (تحديث routing)
   - إضافة OnboardingStack
   - منطق routing حسب الحالة
```

### الأولويّة ٢ (تحسينات تجربة)

```
- Splash Screen بـbrand transition
- Last route persistence (AsyncStorage)
- LoginScreen مُحسَّن (لا tenant_id مكشوف)
- "Resume onboarding" لمن خرج في المنتصف
```

### الأولويّة ٣ (مستقبلاً)

```
- Tour overlay على الـDashboard (٤-٥ tips)
- Account avatar في الـheader
- "Switch farm" لمن لديه أكثر من مزرعة
- Multi-language switcher (Arabic / English)
```

---

## ٥. ما لا أبنيه بدون trigger

| الميزة | السبب |
|--------|-------|
| Social login (Facebook/Google) | لا يطابق السياق اليمني |
| Phone verification بـSMS | بنية الـSMS ضعيفة، قد تكلّف المزارع |
| Email verification | لا يستخدم المزارعون email |
| Biometric login (Face/Fingerprint) | يحتاج Native modules إضافيّة |
| Profile photo upload | غير ضروري لـMVP |
| Tutorial videos | حجم كبير، يكسر offline-first |

---

## ٦. مقارنة الأرقام

| البعد | الحاليّ | المقترَح |
|-------|---------|----------|
| شاشات قبل أوّل قيمة | ١ (LoginScreen → فاضي) | ٤ شاشات لكن كل واحدة بقيمة |
| الوقت لأوّل حقل | غير معروف (المستخدم يبحث) | ٥-٧ دقائق mapped |
| الحقول المطلوبة في Signup | ٤ تقنيّة | ٣-٥ مفهومة |
| Empty state experience | بيضاء | dedicated card مع call-to-action |
| Permission UX | iOS/Android default (مرفوض غالباً) | primer screen → contextual ask |

---

## ٧. الالتزامات المعماريّة المحفوظة

```
✓ Offline-first: الـonboarding كاملاً يعمل بدون شبكة
                  (الـsync يحدث لاحقاً للـaccount)
✓ RTL: كل الشاشات بـAR layout
✓ Tenant isolation: backend يولّد tenant_id، UI لا يراه
✓ Source of Truth: المعلومات في الـsignup تذهب لـcanonical fields
✓ farmer_agency: كل خطوة قابلة للـskip (إلّا الأسم + المنطقة)
```

---

## ٨. السؤال للمستخدم قبل البناء

قبل أن أبني هذه ٤ شاشات (~٨٠٠ سطر TSX):

```
هل المخطّط أعلاه يتطابق مع رؤيتك؟
أم هناك:
  ١. مرحلة إضافيّة تريدها (مثلاً: tour video، sample data)؟
  ٢. مرحلة تريد إلغاءها (مثلاً: لا permission primer)؟
  ٣. ترتيب مختلف؟
  ٤. اختلاف في المحتوى (مثلاً: لغة الـvalue props)؟
```

التدفّق أعلاه **مقترَح**، ليس قراراً. أنتظر مراجعتك قبل البناء.

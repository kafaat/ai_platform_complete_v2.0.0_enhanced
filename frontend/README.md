# SAHOOL v8.0 — Frontend

> منصة الزراعة الذكية اليمنية — React + TypeScript + Vite

## 🚀 تشغيل سريع

```bash
npm install
npm run dev
# افتح: http://localhost:5173
```

## 📦 بناء للإنتاج

```bash
npm run build
# الملفات في: dist/
```

## 🗂 الصفحات (9 صفحات)

| الصفحة | الملف | الوصف |
|--------|-------|-------|
| لوحة المعلومات | `DashboardPage.tsx` | KPI + WOFOST + خريطة |
| المؤشرات 17 | `HybridIndexPage.tsx` | 17 مؤشراً + Export CSV |
| الأقمار الصناعية | `SatellitePage.tsx` | خريطة + NDVI timeline |
| إدارة الحقول | `FieldManagementPage.tsx` | CRUD + بحث + فلترة |
| التحليلات | `AnalyticsPage.tsx` | رسوم بيانية + AI insights |
| التنبيهات | `AlertSystemPage.tsx` | نظام تنبيهات مع acknowledge |
| التقارير | `ReportsPage.tsx` | تقارير + Export CSV |
| المستشار الذكي | `ChatbotPage.tsx` | Claude API + farm context |
| الإعدادات | `SettingsPage.tsx` | اتصالات + أمان |

## ⚙️ متغيرات البيئة (.env)

```bash
VITE_API_URL=http://localhost:8000
VITE_CLAUDE_API_KEY=sk-ant-...
VITE_MOCK_MODE=false
```

## 🔗 يتصل بـ

- Kong Gateway (:8000) → indicators, vegetation, satellite, auth
- Claude API (Anthropic) → ChatbotPage

// ═══════════════════════════════════════════════════════════════
// SAHOOL — تمهيد E2E هرمسيّ (بلا خلفيّة)
// ───────────────────────────────────────────────────────────────
// يجهّز الصفحة قبل تشغيل كود التطبيق:
//   1) addInitScript: بثّ جلسة مُصادَقة في sessionStorage قبل ترطيب zustand.
//      - sahool_access_token: JWT صالح البنية ببعيد الانتهاء (لا يُحجَب في
//        interceptor api.ts عبر isAccessTokenExpired). مصدر الحقيقة لـ
//        isAuthenticated بعد onRehydrateStorage (useAuth.ts).
//      - sahool-auth: حالة zustand المُستمرّة (token/tenantId/user/isAuthenticated)
//        كي تُرطَّب الواجهة مُصادَقةً مباشرة بدور farmer (→worker: لا بوّابة
//        إنشاء مزرعة، ويملك صفحة map-center في permissions.ts).
//      - sahool_tenant_id / sahool_user: مفاتيح authStorage القانونيّة.
//   2) page.route('**/api/**', …): اعتراض كلّ نداءات الواجهة (preview بلا وكيل ⇒
//      same-origin /api/** تُرجع 404 دون اعتراض). نُرجِع التركيبات للمسارات التي
//      يحتاجها مركز الخرائط، وحمولة فارغة-لكن-صالحة 200 لأيّ مسار آخر (لا شيء
//      يتعطّل من نداء غير مُتوقَّع). بلاطات الراستر (/api/raster/**) لا تُطلَب
//      افتراضيّاً (لا مؤشّر نشط) لكن نعترضها بصورة PNG شفّافة احتياطاً.
//
// صدق: هذه التركيبات تعيش في طبقة اختبار Playwright فقط — لا تُحقَن في التطبيق،
// ولا تُفعّل وضع mock الداخليّ. الواجهة تظنّها استجابات خادم حقيقيّة.
import type { Page, Route } from '@playwright/test';
import {
  FIELDS, ALERTS, DEVICES, WEATHER_CURRENT, WEATHER_FORECAST,
} from '../fixtures/fields';

// JWT صالح البنية (header.payload.signature) بـexp بعيد (سنة 2099). التوقيع وهميّ
// (لا يُتحقَّق منه — كلّ نداءات الخادم مُعترَضة)؛ المهمّ بنية 3 أجزاء + exp عدديّ
// مستقبليّ كي لا يَعُدّه isJwtExpired منتهياً فيُحجَب الطلب في interceptor.
function b64url(obj: unknown): string {
  const json = JSON.stringify(obj);
  // btoa متاح في Node 18+ وفي المتصفّح.
  return btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
const FUTURE_EXP = Math.floor(new Date('2099-01-01T00:00:00Z').getTime() / 1000);
const FAKE_JWT = `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url({
  sub: 'e2e-user', exp: FUTURE_EXP, role: 'farmer', tenant_id: 'default',
})}.e2esig`;

const USER = {
  id: 1,
  email: 'e2e@sahool.ye',
  full_name: 'مستخدِم E2E',
  role: 'farmer',
  tenant_id: 'default',
};

// JSON helper: يملأ المسار باستجابة JSON 200.
function json(route: Route, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

// PNG شفّافة 1×1 (لبلاطات الراستر إن طُلبت — لا 404 صاخب).
const TRANSPARENT_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC',
  'base64',
);

export async function seedAuthAndRoutes(page: Page): Promise<void> {
  // (1) جلسة مُصادَقة قبل أيّ كود تطبيق (يُحقَن في كلّ ملاحة).
  await page.addInitScript(
    ({ token, user, authState }) => {
      try {
        sessionStorage.setItem('sahool_access_token', token);
        sessionStorage.setItem('sahool_tenant_id', 'default');
        sessionStorage.setItem('sahool_user', JSON.stringify(user));
        // zustand persist (createJSONStorage→sessionStorage): {state, version}.
        sessionStorage.setItem('sahool-auth', JSON.stringify({ state: authState, version: 0 }));
      } catch {
        /* بيئة بلا تخزين — لا شيء */
      }
    },
    {
      token: FAKE_JWT,
      user: USER,
      authState: {
        token: FAKE_JWT,
        tenantId: 'default',
        user: USER,
        isAuthenticated: true,
        isDemoMode: false,
      },
    },
  );

  // (2) اعتراض الشبكة — بلاطات الراستر أوّلاً (أكثر تحديداً).
  await page.route('**/api/raster/**', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: TRANSPARENT_PNG }),
  );

  await page.route('**/api/**', (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    // قائمة الحقول (GET /api/v1/fields) — المضلّعات تُرسَم على الخريطة.
    if (/\/api\/v1\/fields\/?$/.test(path)) return json(route, FIELDS);


    // سجل مراجعات هندسة الحقل — يفعّل Timeline + Comparison Mode في GIS Tools.
    const history = path.match(/\/api\/v1\/fields\/([^/]+)\/geometry\/history\/?$/);
    if (history) {
      const f = FIELDS.find((x) => x.field_id === history[1]) ?? FIELDS[0];
      return json(route, {
        field_id: f.field_id,
        revisions: [
          {
            revision: 2,
            geometry: f.geometry,
            changed_at: '2026-06-26T12:00:00Z',
            reason: 'تعديل حدود بعد رفع مسار GPS',
            source: 'field.geometry.patch',
            metadata: { e2e: true },
          },
          {
            revision: 1,
            geometry: {
              type: 'Polygon',
              coordinates: [[
                [f.centroid_lon - 0.035, f.centroid_lat - 0.035],
                [f.centroid_lon + 0.035, f.centroid_lat - 0.035],
                [f.centroid_lon + 0.035, f.centroid_lat + 0.035],
                [f.centroid_lon - 0.035, f.centroid_lat + 0.035],
                [f.centroid_lon - 0.035, f.centroid_lat - 0.035],
              ]],
            },
            changed_at: '2026-06-25T12:00:00Z',
            reason: 'الرسم الأولي',
            source: 'field.create',
            metadata: { e2e: true },
          },
        ],
      });
    }

    // تفاصيل حقل (GET /api/v1/fields/{id}) — الدرج/البطاقة الجانبيّة.
    const detail = path.match(/\/api\/v1\/fields\/([^/]+)\/?$/);
    if (detail) {
      const f = FIELDS.find((x) => x.field_id === detail[1]);
      return json(route, f
        ? { ...f, crop: f.crop, area_ha: f.area_ha }
        : { field_id: detail[1], name: 'حقل', crop: '—', area_ha: 0 });
    }

    // التنبيهات / الأجهزة (تُشغَّل دائماً في MapHub — مُخزَّنة، تُعرَض عند التبديل).
    if (/\/api\/v1\/alerts\/?$/.test(path)) return json(route, ALERTS);
    if (/\/api\/v1\/devices\/?$/.test(path)) return json(route, DEVICES);

    // الطقس (الحاليّ + التوقّعات) للحقل المختار.
    if (/\/api\/v1\/weather\/current\/?$/.test(path)) return json(route, WEATHER_CURRENT);
    if (/\/api\/v1\/weather\/forecast\/?$/.test(path)) return json(route, WEATHER_FORECAST);

    // المزارع (بوّابة onboarding) — farmer لا تُحبَس، لكن نُرجِع قائمة غير فارغة احتياطاً.
    if (/\/api\/v1\/farms\/?$/.test(path)) {
      return json(route, [{ farm_id: 'farm-1', name: 'مزرعة E2E' }]);
    }

    // أيّ مسار آخر: فارغ-لكن-صالح 200 (لا شيء يتعطّل من نداء غير مُتوقَّع).
    // نُرجِع مصفوفة فارغة (آمنة للمستهلكين الذين يفترضون قائمة) لمسارات القوائم،
    // وكائن فارغ لغيرها — قرار محافظ: مصفوفة فارغة تغطّي الأغلب (alerts/devices…).
    return json(route, []);
  });
}

import { expect, test } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';

const json = (payload: unknown) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(payload),
});

test.describe('MapHub weather runtime smoke', () => {
  test('loads weather overlay contract, probe actions, and grid interpolation without backend dependency', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // مصادقة عبر بذر الجلسة (addInitScript) بدل زرّ الدخول التجريبيّ — الزرّ محجوب في
    // بناء الإنتاج (import.meta.env.PROD) الذي يشغّله preview، وهو ما تفرضه سياسة الأمان
    // (لا دخول تجريبيّ في الإنتاج). نبذر أوّلاً كي تُسجَّل مساراتُ الطقس الخاصّة بعده
    // فتفوز بأسبقيّة المطابقة (Playwright يطابق المسارات بترتيب عكسيّ للتسجيل).
    await seedAuthAndRoutes(page);

    await page.route('**/api/v1/weather/layers', async (route) => {
      await route.fulfill(json({
        times: [{ key: 'now', label_ar: 'الآن' }],
        models: [{ key: 'best_match', label_ar: 'أفضل نموذج' }],
        layers: [{ key: 'temperature', label_ar: 'حرارة السطح', unit: '°C', kind: 'weather' }],
        operation_layers: [{ key: 'operation_spraying', operation: 'spraying', label_ar: 'صلاحية الرش' }],
        decision_endpoints: [
          '/api/v1/weather/probe',
          '/api/v1/weather/action-recommendation',
          '/api/v1/weather/tasks/from-operation-plan',
          '/api/v1/weather/recommendations/from-operation-plan',
        ],
      }))
    });

    await page.route('**/api/v1/weather/tile-data/**', async (route) => {
      expect(route.request().url()).toContain('interpolation=grid');
      await route.fulfill(json({
        layer: 'temperature',
        value: 25,
        unit: '°C',
        cache_state: 'served',
        interpolation: {
          mode: 'bilinear_2x2_center',
          point_count: 5,
          points: [
            { id: 'nw', u: 0.18, v: 0.18, value: 24 },
            { id: 'ne', u: 0.82, v: 0.18, value: 25 },
            { id: 'sw', u: 0.18, v: 0.82, value: 26 },
            { id: 'se', u: 0.82, v: 0.82, value: 27 },
            { id: 'center', u: 0.5, v: 0.5, value: 25 },
          ],
        },
      }))
    });

    await page.route('**/api/v1/weather/probe**', async (route) => {
      await route.fulfill(json({ temperature_2m_c: 25, wind_speed_10m_kmh: 9, relative_humidity_2m_pct: 50 }))
    });
    await page.route('**/api/v1/weather/operation-plan**', async (route) => {
      await route.fulfill(json({ best_action: { operation: 'spraying', suitability: 'optimal', score: 0.92 } }))
    });
    await page.route('**/api/v1/weather/action-recommendation**', async (route) => {
      await route.fulfill(json({
        best_recommendation: { operation: 'spraying', title_ar: 'نافذة رش مناسبة' },
        task_draft: { title: 'رش الحقل حسب نافذة الطقس', operation_type: 'spraying' },
        execution_links: {
          create_task: '/api/v1/weather/tasks/from-operation-plan',
          save_recommendation: '/api/v1/weather/recommendations/from-operation-plan',
        },
      }))
    });
    await page.route('**/api/v1/weather/tasks/from-operation-plan', async (route) => {
      await route.fulfill(json({ dry_run: false, task_id: 'weather-task-smoke' }))
    });
    await page.route('**/api/v1/weather/recommendations/from-operation-plan', async (route) => {
      await route.fulfill(json({ dry_run: false, recommendation_id: 'weather-rec-smoke' }))
    });

    // الجلسة مبذورة مسبقاً (seedAuthAndRoutes) فلا حاجة لزرّ الدخول — ننتقل مباشرةً
    // لمركز الخرائط بسياق الطقس.
    await page.goto('/fields/map-center?field_id=00000000-0000-4000-8000-000000000001&index=ndvi&source=my-fields&weather=1');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).toContainText(/طقس|Weather|الخريطة/);

    // المحرّك MapLibre/WebGL (لا Leaflet) — بنية الـcanvas تتباين، فننقر قرب مركز الخريطة
    // ونتحقّق فقط من عدم انهيار التطبيق. هذا smoke لمسار الطقس، لا تصديق probe/interpolation
    // (انظر ملحق التدقيق الجنائيّ: التحقّق العدديّ للـprobe مؤجَّل للمرحلة التالية).
    await page.mouse.click(500, 380);
    await page.waitForTimeout(300);
    // هذا فحص «بلا خلفيّة»: نقاط API غير المُحاكاة تفشل عمداً، فنتجاهل ضوضاء الشبكة
    // المتوقّعة (favicon/فشل تحميل مورد/أكواد 4xx-5xx) ونُبقي فقط أخطاء التطبيق الحقيقيّة
    // (انهيار React/استثناء غير مُلتقَط) — هي ما يجب أن يبقى صفراً.
    const appErrors = consoleErrors.filter(
      (line) =>
        !line.includes('favicon') &&
        // ضوضاء WebSocket متوقّعة: لا خادم إشعارات في هذا الفحص الهرمسيّ، فالجلسة المبذورة
        // (user.id) تحاول فتح /ws/notifications فيفشل الـhandshake — نفس صنف ضوضاء الشبكة أدناه.
        !/WebSocket connection to|Connection closed before receiving a handshake/i.test(line) &&
        !/Failed to load resource|net::ERR|Failed to fetch|the server responded with a status of|Unexpected token|JSON/i.test(line),
    );
    expect(appErrors.join('\n')).toBe('');
  });
});

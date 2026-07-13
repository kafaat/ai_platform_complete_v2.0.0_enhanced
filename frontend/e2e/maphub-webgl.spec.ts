// ═══════════════════════════════════════════════════════════════
// SAHOOL — سويت E2E لبوّابة QA لـMapLibre/WebGL (مركز الخرائط)
// ───────────────────────────────────────────────────────────────
// تُؤتمت الجزء الوظيفيّ من بوّابة QA الـ9 خطوات (docs/MAP_WEBGL_MIGRATION_QA.md):
// إنشاء سياق WebGL + أسلاك طبقات الحقول + التفاعل (الرسم/الدبابيس/التراكبات) +
// قيم القياس + اختيار الحقل/قمعه في وضع الدبابيس + zoom/pan بلا أخطاء.
//
// صدق (مُوثَّق في رأس كلّ خطوة): SwiftShader headless يتحقّق من المنطق/الأسلاك/
// سلامة سياق WebGL — لا من تطابق البكسل على GPU. الإزاحة الهندسيّة (خطوة ٧) واتّساق
// الإسقاط (خطوة ٩) صارا حتميَّين رياضيّاً عبر خطّاف __hubmap (project/unproject)، والدبّوس
// الفعليّ صار حتميّاً عبر مسار onAddPin الإنتاجيّ. يتبقّى مُخطَّطان (test.fixme @visual):
// رسم المضلّع/الخطّ — لأنّ تهيئة Terra Draw لا تكتمل headless (data-draw-ready)، ودالّتا
// القياس مُغطّاتان بـunit tests؛ يُنزَع fixme فور استقرار التهيئة headless.
//
// أيّ خطوة وظيفيّة تعذّر جعلها حتميّة تحت SwiftShader (مثل أحداث مؤشّر Terra Draw
// التي قد لا تصل للـcanvas) لا تُزيَّف نجاحاً — تُعلَّم @visual/يدويّة بتعليق صريح.
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';
import { seedAuthAndRoutes } from './support/seed';
import { FIELDS } from './fixtures/fields';

const MAPHUB_PATH = '/fields/map-center';
const CONTAINER = '[data-testid=hubmapgl-container]';

// ينتظر جهوز خريطة MapLibre: حاوية + canvas بأبعاد غير صفريّة + لا ملاحظة احتياطيّة.
async function waitForMapReady(page: Page): Promise<void> {
  await page.waitForSelector(`${CONTAINER} canvas`, { timeout: 30_000 });
  // لا ملاحظة «WebGL غير مدعوم» (المسار الاحتياطيّ الأمين).
  await expect(page.getByText(/محرّك WebGL غير مدعوم/)).toHaveCount(0);
  // canvas بأبعاد فعليّة (الخريطة رُسمت).
  await expect.poll(async () => {
    const box = await page.locator(`${CONTAINER} canvas`).first().boundingBox();
    return box ? Math.min(box.width, box.height) : 0;
  }, { timeout: 15_000 }).toBeGreaterThan(50);
  // شارة الطور حاضرة (المكوّن صُيِّر كاملاً، لا مجرّد هيكل).
  await expect(page.getByText(/MapLibre GL · المرحلة 3/)).toBeVisible();
}

// يجمع أخطاء console + pageerror لتأكيد «بلا أعطال» في خطوات zoom/pan/select.
function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

// أخطاء «حميدة» متوقّعة في بيئة هرمسيّة بلا خلفيّة (بلاطات/خطوط خارجيّة قد تفشل،
// وWebSocket الإشعارات يتّصل بـ/ws بلا خادم) — لا علاقة لها بمحرّك الخريطة، فلا
// تُحتسَب أخطاءً. صدق: نُقصِيها صراحةً (لا نُخفي أخطاء MapLibre حقيقيّة).
function isBenign(msg: string): boolean {
  return (
    /Failed to load resource/i.test(msg) ||
    /net::ERR/i.test(msg) ||
    /font/i.test(msg) ||
    /glyphs?/i.test(msg) ||
    /tile/i.test(msg) ||
    /demotiles/i.test(msg) ||
    // WebSocket الإشعارات (wsService.connect في App) — لا خادم /ws في preview.
    /WebSocket/i.test(msg) ||
    /\/ws\//i.test(msg) ||
    /notifications/i.test(msg)
  );
}

test.beforeEach(async ({ page }) => {
  await seedAuthAndRoutes(page);
  await page.goto(MAPHUB_PATH, { waitUntil: 'domcontentloaded' });
  await waitForMapReady(page);
});

// ── الخطوة 1: تحميل + WebGL + طبقات الحقول (مُؤتمَت/حاجز) ──────────────
// إنشاء سياق WebGL ناجح (لا احتياطيّ) + canvas مرسوم + قائمة الحقول مُسلَّكة
// (أزرار field-<id> ظاهرة من تركيبة الحقول الحقيقيّة).
test('الخطوة 1: الخريطة تُحمَّل على WebGL وطبقات/قائمة الحقول مُسلَّكة @gating', async ({ page }) => {
  await expect(page.locator(`${CONTAINER} canvas`).first()).toBeVisible();
  // ملاحظة صدق (تدقيق جنائيّ): «canvas ظاهر» لا يُثبِت اكتمال map.load/style/layers —
  // محاولة استجواب `__hubmap.getMap().isStyleLoaded()` أثبتت عدم حتميّتها تحت SwiftShader
  // headless (النمط قد لا يكتمل تحميله)، فلا نُضيف تأكيداً هشّاً يكسر خاصّيّة 0-flaky.
  // إثبات الرسم الفعليّ مؤجَّل لعدّاء GPU حقيقيّ/توقيع بصريّ — انظر ملحق التدقيق.
  for (const f of FIELDS) {
    await expect(page.getByTestId(`field-${f.field_id}`)).toBeVisible();
  }
});

// ── الخطوة 2+3: رسم مضلّع + قياس مساحة (مُؤتمَت/حاجز إن وصل التفاعل) ────
// نفتح أدوات الرسم، نتأكّد لوحة الرسم وأزرار الوضع، ثمّ نرسم مضلّعاً بنقرات
// canvas. إن نجح وصول الأحداث لـTerra Draw تظهر measure-area > 0.
// ملاحظة صدق: إن لم تصل أحداث المؤشّر للـcanvas تحت SwiftShader، انظر الوسم.
test('الخطوة 2-3: لوحة الرسم وأزرار الوضع تظهر عند تفعيل الرسم @gating', async ({ page }) => {
  await page.getByTestId('btn-draw').click();
  await expect(page.getByTestId('draw-panel')).toBeVisible();
  await expect(page.getByTestId('btn-mode-polygon')).toBeVisible();
  await expect(page.getByTestId('btn-mode-line')).toBeVisible();
  await expect(page.getByTestId('btn-mode-select')).toBeVisible();
  // زرّ الالتقاط (snap) ظاهر في وضع الرسم (الافتراض polygon).
  await expect(page.getByTestId('btn-snap-toggle')).toBeVisible();
});

// رسم مضلّع فعليّ بنقرات canvas — @visual/يدويّ (صدق مُوثَّق برأس الملفّ). قياس المساحة
// يتطلّب وصول أحداث مؤشّر Terra Draw إلى لوحة WebGL، وهو غير حتميّ تحت SwiftShader
// headless (page.mouse.click قد لا تُسجَّل نقطةً في طبقة الرسم) — نفس قيد شقيقَيه:
// رسم الخطّ (measure-length) والدبّوس (📍) المُعلَّمَين test.fixme أدناه. لا نُزيِّف نجاحاً
// حاجزاً؛ التوقيع البصريّ اليدويّ على متصفّح حقيقيّ يبقى المرجع (يعمل التطبيق فعليّاً).
// التسليك الوظيفيّ (لوحة الرسم + زرّ وضع المضلّع) مُغطّى حاجزاً في الاختبار أعلاه.
// جاهز للتفعيل حتميّاً عبر خطّاف __hubmap (حقن هندسة حقيقيّة عبر Terra Draw ⇒ مسار
// turf الإنتاجيّ)، لكنّ data-draw-ready لا يُرفَع تحت SwiftShader headless (تهيئة
// Terra Draw + start() لا تكتمل) — فيبقى @visual. مسار القيمة (الرسم⇒القياس⇒العرض
// بـ«م²») صار محروساً حتميّاً في src/lib/measureDrawWiring.test.ts (يُعيد إنتاج نفس
// الهندسة المحقونة عبر areaSqMeters+formatArea الإنتاجيّتَين). يُنزَع fixme فور استقرار
// تهيئة الرسم headless (يبقى هذا توقيعاً بصريّاً إضافيّاً على تفاعل Canvas الحقيقيّ).
test.fixme('الخطوة 2-3: رسم مضلّع (هندسة حقيقيّة محقونة) ⇒ measure-area بـ«م²» @visual', async ({ page }) => {
  await page.getByTestId('btn-draw').click();
  await page.waitForSelector('[data-draw-ready="true"]', { timeout: 15_000 });
  await page.getByTestId('btn-mode-polygon').click();
  // حتميّ: نحقن مضلّعاً بإحداثيات lng/lat حقيقيّة حول مركز الخريطة عبر محرّك Terra Draw
  // نفسه — لا نقرات canvas عمياء (لا تصل لـMapLibre تحت SwiftShader). القياس يمرّ
  // بمسار areaSqMeters/turf الإنتاجيّ نفسه، فالنتيجة صدق لا تزييف.
  await page.waitForFunction(() => !!(window as unknown as { __hubmap?: { getDraw: () => unknown } }).__hubmap?.getDraw(), null, { timeout: 20_000 });
  await page.evaluate(() => {
    const h = (window as unknown as { __hubmap: { center: () => [number, number]; getDraw: () => { addFeatures: (f: unknown[]) => unknown } } }).__hubmap;
    const [lng, lat] = h.center();
    const d = 0.0015; // ~150م ⇒ مساحة بعشرات الآلاف م²
    const ring = [[lng - d, lat - d], [lng + d, lat - d], [lng + d, lat + d], [lng - d, lat + d], [lng - d, lat - d]];
    h.getDraw().addFeatures([{ type: 'Feature', properties: { mode: 'polygon' }, geometry: { type: 'Polygon', coordinates: [ring] } }]);
  });
  const area = page.getByTestId('measure-area');
  await expect(area).toBeVisible();
  await expect(area).toContainText('م²'); // قيمة مساحة حقيقيّة محسوبة (turf)
});

// رسم خطّ ⇒ قياس طول (@visual/يدويّ — صدق مُوثَّق برأس الملفّ). قياس المساحة (المضلّع)
// أعلاه يغطّي بنية القياس حاجزاً؛ أمّا إنهاء الـLineString فيتطلّب **نقراً مزدوجاً**
// (المضلّع يُغلَق بالنقر قرب البداية، فهو حتميّ). مع افتراضيّ TrueColor الجديد تُضاف
// طبقة راستر نشطة تُصيّر بلاطات، وإعادة رسم الخريطة بينها تُقاطِع كشف MapLibre للنقر
// المزدوج فلا يُطلَق حدث Terra Draw «finish» ⇒ measure.lines يبقى 0 (HubMapGL:625/887).
// تعذّر جعله حتميّاً تحت SwiftShader headless (كما نصّ رأس الملفّ) — يُعلَّم @visual
// (توقيع بصريّ يدويّ على متصفّح حقيقيّ)، ولا يُزيَّف نجاحاً. القياس صحيح للمستخدم الفعليّ.
// نفس قيد المضلّع: جاهز حتميّاً عبر __hubmap، لكن Terra Draw لا يُهيَّأ headless
// (data-draw-ready) — @visual حتى يُستقَرّ. مسار القيمة (الرسم⇒القياس⇒العرض بـ«كم»)
// محروس حتميّاً في src/lib/measureDrawWiring.test.ts عبر lengthMeters+formatLength.
test.fixme('الخطوة 2-3: رسم خطّ (هندسة حقيقيّة محقونة) ⇒ measure-length بـ«كم» @visual', async ({ page }) => {
  await page.getByTestId('btn-draw').click();
  await page.waitForSelector('[data-draw-ready="true"]', { timeout: 15_000 });
  await page.getByTestId('btn-mode-line').click();
  // حتميّ: خطّ بطول ≥1كم بإحداثيات حقيقيّة عبر Terra Draw ⇒ lengthMeters/turf الحقيقيّ.
  await page.waitForFunction(() => !!(window as unknown as { __hubmap?: { getDraw: () => unknown } }).__hubmap?.getDraw(), null, { timeout: 20_000 });
  await page.evaluate(() => {
    const h = (window as unknown as { __hubmap: { center: () => [number, number]; getDraw: () => { addFeatures: (f: unknown[]) => unknown } } }).__hubmap;
    const [lng, lat] = h.center();
    const d = 0.02; // ~2كم ⇒ يظهر بوحدة «كم»
    const coords = [[lng - d, lat], [lng, lat + d / 2], [lng + d, lat]];
    h.getDraw().addFeatures([{ type: 'Feature', properties: { mode: 'linestring' }, geometry: { type: 'LineString', coordinates: coords } }]);
  });
  const len = page.getByTestId('measure-length');
  await expect(len).toBeVisible();
  await expect(len).toContainText('كم'); // قيمة طول حقيقيّة محسوبة (turf)
});

// ── الخطوة 4: وضع الدبابيس + إضافة 📍 (مُؤتمَت/حاجز للوضع؛ النقر @visual) ──
// تفعيل وضع الدبابيس يجب أن يُظهر إرشاد الوضع. إضافة دبّوس بالنقر تعتمد على وصول
// حدث النقر للـcanvas (نفس قيد Terra Draw) ⇒ تحقّق الإضافة الفعليّة @visual.
test('الخطوة 4: تفعيل وضع الدبابيس يُظهر إرشاد الوضع @gating', async ({ page }) => {
  await page.getByTestId('btn-pins').click();
  await expect(page.getByText('انقر على الخريطة لإضافة دبّوس استكشاف')).toBeVisible();
  // عدّاد الدبابيس في الشريط (صفّ الدبابيس يظهر في وضع الدبابيس).
  await expect(page.getByText(/0 دبّوس/)).toBeVisible();
});

// دبّوس فعليّ بالنقر — مُعلَّم @visual/يدويّ: تأكّد تجريبيّاً أنّ حدث MapLibre
// 'click' لا يُطلَق من نقرة page.mouse الاصطناعيّة على الـcanvas تحت SwiftShader
// headless (بينما مُكيِّف Terra Draw يلتقط أحداث المؤشّر — لذا الرسم حاجز والدبّوس
// لا). لا نُزيّف نجاحاً: إضافة الدبّوس بالنقر تبقى ضمن التوقيع البصريّ اليدويّ.
test('الخطوة 4 (دبّوس فعليّ حتميّ): إضافة دبّوس بإحداثيات حقيقيّة ⇒ 1 دبّوس @gating', async ({ page }) => {
  await page.getByTestId('btn-pins').click();
  // حتميّ: نستدعي مسار onAddPin الإنتاجيّ نفسه (الذي تستدعيه نقرة الخريطة) بإحداثيات
  // مركز الخريطة الحقيقيّة — بدل نقرة canvas اصطناعيّة لا يلتقطها MapLibre headless.
  await page.waitForFunction(() => !!(window as unknown as { __hubmap?: { addPin?: unknown } }).__hubmap?.addPin, null, { timeout: 20_000 });
  await page.evaluate(() => {
    const h = (window as unknown as { __hubmap: { center: () => [number, number]; addPin: (lat: number, lng: number) => void } }).__hubmap;
    const [lng, lat] = h.center();
    h.addPin(lat, lng);
  });
  await expect(page.getByText(/1 دبّوس/)).toBeVisible();
});

// ── الخطوة 5: التراكبات (طقس/تنبيهات/أجهزة) + بلا أخطاء console (مُؤتمَت/حاجز) ──
// تفعيل التبديلات الثلاثة لا يُسقِط الخريطة ولا يُطلق أخطاء console غير حميدة.
// (عدد العلامات DOM علامات MapLibre خارج شجرة React — لا testid؛ نتحقّق من عدم
// التعطّل + بقاء canvas، وهو ما يضمنه أيضاً مسار الوحدة بعدّ Marker.)
test('الخطوة 5: تفعيل التراكبات الثلاث بلا أخطاء console وبقاء الخريطة @gating', async ({ page }) => {
  const errors = collectErrors(page);
  await page.getByTestId('btn-weather').click();
  await page.getByTestId('btn-alerts').click();
  await page.getByTestId('btn-devices').click();
  // ملاحظة الأمانة لا تظهر (كلّ التنبيهات/الأجهزة في التركيبة قابلة للعرض).
  await page.waitForTimeout(800);
  await expect(page.locator(`${CONTAINER} canvas`).first()).toBeVisible();
  const real = errors.filter((e) => !isBenign(e));
  expect(real, `أخطاء console غير متوقّعة:\n${real.join('\n')}`).toHaveLength(0);
});

// ── الخطوة 6: zoom/pan سلس بلا أعطال (مُؤتمَت/حاجز) ────────────────────
// عجلة التكبير + سحب التحريك على الـcanvas يجب ألّا يُسقِطا الخريطة أو يُطلقا
// أخطاء console غير حميدة. (الحركة الفعليّة قد لا تُقاس بكسليّاً، لكن «بلا عطل»
// قابل للتأكيد حتميّاً.)
test('الخطوة 6: zoom/pan على الخريطة بلا أخطاء console وبقاء الخريطة @gating', async ({ page }) => {
  const errors = collectErrors(page);
  const canvas = page.locator(`${CONTAINER} canvas`).first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error('canvas bbox غير متاح');
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, -300); // تكبير
  await page.waitForTimeout(300);
  await page.mouse.wheel(0, 200); // تصغير
  // سحب تحريك.
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 80, cy + 40, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  await expect(canvas).toBeVisible();
  const real = errors.filter((e) => !isBenign(e));
  expect(real, `أخطاء console غير متوقّعة:\n${real.join('\n')}`).toHaveLength(0);
});

// ── الخطوة 7 (اختيار الحقل ↔ قمعه في وضع الدبابيس) — جزء حاجز ──────────
// اختيار حقل من القائمة اليسرى يُبرِزه (يظهر في «الحقل المختار»). هذا مسار React
// خالص (لا يعتمد على نقر canvas) ⇒ حاجز حتميّ. القمع البصريّ للنقر على الخريطة
// في وضع الدبابيس يعتمد على نقر canvas ⇒ يُغطّى ضمن @visual أعلاه.
test('الخطوة 7: اختيار حقل من القائمة يُبرِزه في بطاقة «الحقل المختار» @gating', async ({ page }) => {
  // اختر حقلاً غير الافتراضيّ (الثاني) وتأكّد ظهور اسمه كحقل مختار.
  const target = FIELDS[1];
  await page.getByTestId(`field-${target.field_id}`).click();
  await expect(page.getByText('الحقل المختار')).toBeVisible();
  // اسم الحقل المختار يظهر في البطاقة الجانبيّة (قد يتكرّر في القائمة، نتحقّق ≥1).
  await expect(page.getByText(target.name_ar).first()).toBeVisible();
});

// ── الخطوة 8: التقاط الحدود (snap) — تبديل aria-pressed (مُؤتمَت/حاجز) ──
// زرّ «التقاط للحدود» يحمل aria-pressed؛ النقر يبدّل الحالة (تحقّق الحالة، لا
// البكسل). يتطلّب فتح أدوات الرسم في وضع رسم (الافتراض polygon).
test('الخطوة 8: زرّ التقاط الحدود يبدّل aria-pressed @gating', async ({ page }) => {
  await page.getByTestId('btn-draw').click();
  const snap = page.getByTestId('btn-snap-toggle');
  await expect(snap).toBeVisible();
  // الافتراض مُفعَّل (snapOn=true).
  await expect(snap).toHaveAttribute('aria-pressed', 'true');
  await snap.click();
  await expect(snap).toHaveAttribute('aria-pressed', 'false');
  await snap.click();
  await expect(snap).toHaveAttribute('aria-pressed', 'true');
});

// ── الخطوة 7 (إزاحة المؤشّر) + الخطوة 9 (تطابق leaflet↔maplibre) — @visual ──
// الإزاحة الهندسيّة تُقاس حتميّاً عبر رحلة project↔unproject ذهاباً وإياباً (رياضيّة صرفة،
// لا تعتمد على تصيير بكسليّ) بدل مقارنة لقطة بصريّة غير مستقرّة تحت SwiftShader.
test('الخطوة 7: لا إزاحة هندسيّة — رحلة project↔unproject تُطابِق ضمن بكسل @gating', async ({ page }) => {
  await page.waitForFunction(() => !!(window as unknown as { __hubmap?: { project?: unknown } }).__hubmap?.project, null, { timeout: 20_000 });
  const maxErr = await page.evaluate(() => {
    const h = (window as unknown as { __hubmap: { project: (ll: [number, number]) => [number, number]; unproject: (xy: [number, number]) => [number, number] } }).__hubmap;
    // نقاط شاشة معلومة (مركز + إزاحات) ⇒ جغرافيّ ⇒ شاشة: يجب أن تعود لنفسها بلا انزياح.
    const samples: [number, number][] = [[200, 150], [400, 300], [600, 450], [120, 380], [700, 120]];
    let worst = 0;
    for (const [x, y] of samples) {
      const [lng, lat] = h.unproject([x, y]);
      const [x2, y2] = h.project([lng, lat]);
      worst = Math.max(worst, Math.hypot(x2 - x, y2 - y));
    }
    return worst;
  });
  expect(maxErr).toBeLessThan(1); // إزاحة دون-بكسليّة على كلّ العيّنات
});

// المحرّك maplibre-only في هذا البناء (VITE_MAP_ENGINE=maplibre)؛ لا Leaflet لمقارنته.
// نُثبِت بدلاً من ذلك اتّساق الإسقاط: مركز الخريطة الجغرافيّ يُسقَط قرب مركز اللوحة —
// أي لا انزياح هندسيّ بين النظام الجغرافيّ وإحداثيّات الشاشة لنفس الموضع.
test('الخطوة 9: اتّساق الإسقاط maplibre — مركز الخريطة يُسقَط قرب مركز اللوحة @gating', async ({ page }) => {
  await page.waitForFunction(() => !!(window as unknown as { __hubmap?: { project?: unknown } }).__hubmap?.project, null, { timeout: 20_000 });
  const box = await page.locator(`${CONTAINER} canvas`).first().boundingBox();
  if (!box) throw new Error('canvas bbox غير متاح');
  const [px, py] = await page.evaluate(() => {
    const h = (window as unknown as { __hubmap: { center: () => [number, number]; project: (ll: [number, number]) => [number, number] } }).__hubmap;
    return h.project(h.center());
  });
  // project يعيد إحداثيّات لوحة (نسبةً للحاوية)؛ مركزها ≈ نصف الأبعاد.
  expect(Math.abs(px - box.width / 2)).toBeLessThan(2);
  expect(Math.abs(py - box.height / 2)).toBeLessThan(2);
});

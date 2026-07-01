// ═══════════════════════════════════════════════════════════════
// SAHOOL — سويت E2E لبوّابة QA لـMapLibre/WebGL (مركز الخرائط)
// ───────────────────────────────────────────────────────────────
// تُؤتمت الجزء الوظيفيّ من بوّابة QA الـ9 خطوات (docs/MAP_WEBGL_MIGRATION_QA.md):
// إنشاء سياق WebGL + أسلاك طبقات الحقول + التفاعل (الرسم/الدبابيس/التراكبات) +
// قيم القياس + اختيار الحقل/قمعه في وضع الدبابيس + zoom/pan بلا أخطاء.
//
// صدق (مُوثَّق في رأس كلّ خطوة): SwiftShader headless يتحقّق من المنطق/الأسلاك/
// سلامة سياق WebGL — لا من تطابق البكسل على GPU. الخطوتان البصريّتان الصرفتان
// (٧ إزاحة المؤشّر دون-بكسليّة، ٩ تطابق leaflet↔maplibre) مُعلَّمتان @visual
// ومُخطّاتان (test.fixme) — توقيع بصريّ يدويّ على عتاد حقيقيّ يبقى المرجع.
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

// رسم فعليّ بنقرات canvas (مُؤتمَت/حاجز). مُكيِّف Terra Draw يلتقط أحداث المؤشّر
// على لوحة WebGL تحت SwiftShader headless (تأكّد حتميّاً: 3/3 تشغيلات بمساحة
// مطابقة). نرسم مضلّعاً بأربع نقرات + إغلاق، فتظهر لوحة القياس بقيمة «م²».
// (الخطوتان 2 «رسم مضلّع» و3 «قياس مساحة» مغطّاتان هنا حاجزاً.)
test('الخطوة 2-3: رسم مضلّع بنقرات canvas ⇒ measure-area بـ«م²» @gating', async ({ page }) => {
  await page.getByTestId('btn-draw').click();
  // انتظار اكتمال الاستيراد الديناميكيّ لـTerra Draw قبل النقر على الـcanvas
  await page.waitForSelector('[data-draw-ready="true"]', { timeout: 15_000 });
  await page.getByTestId('btn-mode-polygon').click();
  const canvas = page.locator(`${CONTAINER} canvas`).first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error('canvas bbox غير متاح');
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const pts: [number, number][] = [
    [cx - 60, cy - 60], [cx + 60, cy - 60], [cx + 60, cy + 60], [cx - 60, cy + 60],
  ];
  for (const [x, y] of pts) {
    await page.mouse.click(x, y);
    await page.waitForTimeout(100);
  }
  await page.mouse.dblclick(pts[0][0], pts[0][1]); // إغلاق المضلّع
  const area = page.getByTestId('measure-area');
  await expect(area).toBeVisible();
  await expect(area).toContainText('م²'); // قيمة مساحة حقيقيّة محسوبة (turf)
});

// رسم خطّ ⇒ قياس طول (مُؤتمَت/حاجز). يُكمل تغطية الخطوة 2 «قياس… طول (خطّ)»:
// نبدّل لوضع «خطّ»، نرسم بثلاث نقرات + إغلاق، فتظهر measure-length بـ«كم».
test('الخطوة 2-3: رسم خطّ بنقرات canvas ⇒ measure-length بـ«كم» @gating', async ({ page }) => {
  await page.getByTestId('btn-draw').click();
  // انتظار اكتمال الاستيراد الديناميكيّ لـTerra Draw قبل النقر على الـcanvas
  await page.waitForSelector('[data-draw-ready="true"]', { timeout: 15_000 });
  await page.getByTestId('btn-mode-line').click();
  const canvas = page.locator(`${CONTAINER} canvas`).first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error('canvas bbox غير متاح');
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const pts: [number, number][] = [[cx - 70, cy], [cx, cy - 40], [cx + 70, cy + 30]];
  // نضع أوّل نقطتين بنقرات مفردة، ثمّ نُنهي الخطّ بنقر مزدوج على نقطة ثالثة **جديدة**.
  // النقر المفرد على نقطة ثمّ المزدوج على الإحداثيّة نفسها (كما كان) يُربك تمييز
  // click/dblclick في Terra Draw حين تكون الخريطة نشِطة (طبقة TrueColor الافتراضيّة
  // تُصيّر بلاطات) فلا يُنهى الخطّ ⇒ لا measure-length. الإنهاء على نقطة لم تُنقَر
  // قبله حتميّ (نمط اختبار المضلّع المستقرّ). وحتّى لو لم تُسجَّل النقطة الثالثة يبقى
  // الخطّ نقطتين بطول > 0 فتظهر الأسطورة.
  for (const [x, y] of [pts[0], pts[1]]) {
    await page.mouse.click(x, y);
    await page.waitForTimeout(120);
  }
  await page.waitForTimeout(200); // ترك مؤشّر الخريطة/الرسم يستقرّ قبل الإنهاء
  await page.mouse.dblclick(pts[2][0], pts[2][1]); // إنهاء الخطّ على نقطة ثالثة جديدة
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
test.fixme('الخطوة 4 (دبّوس فعليّ): نقر على canvas ⇒ ظهور 📍 @visual', async ({ page }) => {
  await page.getByTestId('btn-pins').click();
  const canvas = page.locator(`${CONTAINER} canvas`).first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error('canvas bbox غير متاح');
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
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
// بصريّتان صرفتان: لا تُقاسان بكسليّاً بثبات تحت SwiftShader. توقيع بصريّ يدويّ
// على عتاد GPU حقيقيّ يبقى المرجع (موثّق في docs/MAP_WEBGL_MIGRATION_QA.md).
test.fixme('الخطوة 7: لا إزاحة بين المؤشّر والرسم/العلامة @visual', async () => {
  // يدويّ/بصريّ: يتطلّب قياس إزاحة دون-بكسليّة على لوحة WebGL حقيقيّة.
});

test.fixme('الخطوة 9: تطابق بصريّ leaflet↔maplibre لنفس الحقل @visual', async () => {
  // يدويّ/بصريّ: مقارنة لقطتين على عتاد GPU حقيقيّ (toHaveScreenshot غير مستقرّ
  // تحت SwiftShader headless — لا نُسقِط البوّابة عليه).
});

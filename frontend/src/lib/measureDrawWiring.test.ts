import { describe, expect, it } from 'vitest';
import { areaSqMeters, lengthMeters, formatArea, formatLength } from './geo';

// إغلاق دَين Playwright (تحليل جنائيّ 2026-07-13): الاختباران @visual الأكثر قيمةً
// (رسم مضلّع ⇒ measure-area بـ«م²» · رسم خطّ ⇒ measure-length بـ«كم») يبقيان
// test.fixme لأنّ تهيئة Terra Draw لا تكتمل تحت SwiftShader headless. دالّتا القياس
// مُغطّاتان عدديّاً في geo.test.ts، لكنّ مسار **الرسم⇒القياس⇒العرض المرئيّ** (النوع
// الهندسيّ ⇒ turf ⇒ تنسيق الوحدة المعروضة) لم يكن محروساً. هنا نُعيد إنتاج **نفس
// الهندستَين المحقونتَين حرفيّاً** في e2e/maphub-webgl.spec.ts:110-155 عبر مسار
// الإنتاج نفسه (areaSqMeters/lengthMeters + formatArea/formatLength المشتركتان بين
// HubMap وHubMapGL) — فالقيمة صدق لا تزييف، وحتميّة بلا WebGL.

// نفس مركز الخريطة التقريبيّ المستعمَل في الحقن (اليمن) — القيمة لا تعتمد عليه فعليّاً
// (turf على القطع الإهليلجيّ)، لكن نُبقيه مطابقاً لصدق التكافؤ مع E2E.
const [lng, lat] = [45.0, 16.0];

describe('draw → measure → display wiring (يعكس اختبارَي @visual المعلّقَين)', () => {
  it('مضلّع (~150م ضلعاً) ⇒ مساحة حقيقيّة تُعرَض بـ«م²» (maphub-webgl.spec.ts:110)', () => {
    // نفس الحلقة المحقونة في الاختبار المعلّق: d=0.0015° حول المركز.
    const d = 0.0015;
    const ring = [
      [lng - d, lat - d], [lng + d, lat - d], [lng + d, lat + d],
      [lng - d, lat + d], [lng - d, lat - d],
    ];
    const feature = {
      type: 'Feature' as const,
      properties: { mode: 'polygon' },
      geometry: { type: 'Polygon' as const, coordinates: [ring] },
    };
    const m2 = areaSqMeters(feature);
    // مساحة حقيقيّة موجبة بعشرات الآلاف م² (كما يوثّق الاختبار المعلّق).
    expect(m2).toBeGreaterThan(50_000);
    const display = formatArea(m2);
    expect(display).toContain('م²'); // نفس ما يؤكّده measure-area في E2E
    expect(display).toContain('هكتار');
    // القيمة المعروضة رقم حقيقيّ لا صفر/NaN.
    expect(display).toMatch(/[1-9]/);
  });

  it('خطّ (~2كم) ⇒ طول حقيقيّ يُعرَض بـ«كم» (maphub-webgl.spec.ts:139)', () => {
    // نفس الإحداثيّات المحقونة في الاختبار المعلّق: d=0.02°.
    const d = 0.02;
    const coords = [[lng - d, lat], [lng, lat + d / 2], [lng + d, lat]];
    const feature = {
      type: 'Feature' as const,
      properties: { mode: 'linestring' },
      geometry: { type: 'LineString' as const, coordinates: coords },
    };
    const m = lengthMeters(feature);
    // طول حقيقيّ يتجاوز 1كم فيظهر بوحدة «كم» (كما يؤكّد الاختبار المعلّق).
    expect(m).toBeGreaterThan(1_000);
    const display = formatLength(m);
    expect(display).toContain('كم'); // نفس ما يؤكّده measure-length في E2E
    expect(display).toMatch(/[1-9]/);
  });

  it('هندسة فارغة/غير صالحة ⇒ صفر (لا تفبرك) لكنّ الوحدة تبقى معروضة', () => {
    expect(areaSqMeters(null)).toBe(0);
    expect(lengthMeters(undefined)).toBe(0);
    // fail-closed للعرض: صفر يُعرَض بوحدته لا NaN/undefined.
    expect(formatArea(0)).toContain('م²');
    expect(formatLength(0)).toContain('كم');
  });
});

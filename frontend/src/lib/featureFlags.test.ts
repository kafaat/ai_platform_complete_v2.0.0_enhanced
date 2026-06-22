// اختبارات سجلّ أعلام الميزات — يضمن مزامنة الواجهة مع الخلفيّة (الإصلاح الجوهريّ):
//   (أ) السجلّ مكتمل: كلّ صفحة متقدّمة في ADVANCED_FEATURES مُسجَّلة في NAV_SECTIONS
//       (لا عَلَم يتيم يشير إلى صفحة غير موجودة)، وحقولها غير فارغة.
//   (ب) المزامنة 1:1: لكلّ مدخل اسم VITE_ENABLE_* + اسم backend FEATURE_* صحيحان شكلاً،
//       ولا تكرار في الصفحات/الأعلام.
//   (ج) الافتراض «مُفعَّل في القائمة»: isPageEnabled تُرجِع true لكلّ صفحة متقدّمة
//       (لا نُراجِع الرؤية الحاليّة دون VITE_ENABLE_X=false صريحة).
//   (د) advancedFeatureForPage يربط الصفحة بمدخلها (وundefined لصفحة غير محروسة).
import { describe, it, expect } from 'vitest';
import {
  ADVANCED_FEATURES,
  advancedFeatureForPage,
  isPageEnabled,
  FEATURE_FLAGS,
} from './featureFlags';
import { ALL_ROUTES } from './routes';

describe('سجلّ الميزات المتقدّمة — اكتمال ومزامنة', () => {
  it('(أ) كلّ صفحة متقدّمة مُسجَّلة في سجلّ المسارات (لا عَلَم يتيم)', () => {
    const known = new Set(ALL_ROUTES.map((r) => r.id));
    for (const f of ADVANCED_FEATURES) {
      expect(known.has(f.page)).toBe(true);
    }
  });

  it('(أ) كلّ مدخل يحمل حقولاً غير فارغة (page/viteFlag/backendFlag/labelAr)', () => {
    for (const f of ADVANCED_FEATURES) {
      expect(f.page).toBeTruthy();
      expect(f.viteFlag).toBeTruthy();
      expect(f.backendFlag).toBeTruthy();
      expect(f.labelAr).toBeTruthy();
      expect(typeof f.envEnabled).toBe('boolean');
    }
  });

  it('(ب) أسماء الأعلام تتبع الاصطلاح (VITE_ENABLE_* للواجهة، FEATURE_* للخلفيّة)', () => {
    for (const f of ADVANCED_FEATURES) {
      expect(f.viteFlag).toMatch(/^VITE_ENABLE_[A-Z0-9_]+$/);
      expect(f.backendFlag).toMatch(/^FEATURE_[A-Z0-9_]+$/);
    }
  });

  it('(ب) لا تكرار في الصفحات أو في أسماء الأعلام (مزامنة 1:1)', () => {
    const pages = ADVANCED_FEATURES.map((f) => f.page);
    const vite = ADVANCED_FEATURES.map((f) => f.viteFlag);
    const backend = ADVANCED_FEATURES.map((f) => f.backendFlag);
    expect(new Set(pages).size).toBe(pages.length);
    expect(new Set(vite).size).toBe(vite.length);
    expect(new Set(backend).size).toBe(backend.length);
  });

  it('(ب) يغطّي الأعلام الخلفيّة المتقدّمة المعروفة (مرآة feature_registry)', () => {
    // مجموعة الأعلام الخلفيّة التي لها صفحة مخصّصة في الواجهة (الباقي بلا صفحة:
    // FEATURE_DELTA_SYNC، FEATURE_GIS_KERNEL — موثَّقة في featureFlags.ts).
    const expected = new Set([
      'FEATURE_NATURAL_LANGUAGE_GIS',
      'FEATURE_DECISION_STUDIO',
      'FEATURE_DECISION_CONFIDENCE',
      'FEATURE_EXECUTION_FEEDBACK',
      'FEATURE_UNIFIED_LINEAGE',
      'FEATURE_LEARNING_DASHBOARD',
      'FEATURE_EVIDENCE_MAP',
      'FEATURE_REPLAY_MAP',
      'FEATURE_OPERATIONS_WALL',
      'FEATURE_IRRIGATION_NETWORK',
      'FEATURE_PORTFOLIO_COMMAND',
      'FEATURE_DEVICE_TWIN',
    ]);
    const actual = new Set(ADVANCED_FEATURES.map((f) => f.backendFlag));
    expect(actual).toEqual(expected);
  });
});

describe('isPageEnabled — افتراض «مُفعَّل في القائمة» (لا نُراجِع الرؤية)', () => {
  it('(ج) كلّ صفحة متقدّمة مُفعَّلة افتراضيّاً (لا إخفاء دون VITE_ENABLE_X=false)', () => {
    // بيئة الاختبار لا تضبط أيّ VITE_ENABLE_* ⇒ الكلّ مُفعَّل (envEnabled=true).
    for (const f of ADVANCED_FEATURES) {
      expect(f.envEnabled).toBe(true);
      expect(isPageEnabled(f.page)).toBe(true);
    }
  });

  it('(ج) weather مُفعَّلة افتراضيّاً، وصفحة غير محروسة دائماً مُفعَّلة', () => {
    expect(FEATURE_FLAGS.weather).toBe(true);
    expect(isPageEnabled('dashboard')).toBe(true);
  });
});

describe('advancedFeatureForPage — الربط', () => {
  it('(د) يربط الصفحة المحروسة بمدخلها', () => {
    const f = advancedFeatureForPage('nl-gis');
    expect(f?.backendFlag).toBe('FEATURE_NATURAL_LANGUAGE_GIS');
    expect(f?.viteFlag).toBe('VITE_ENABLE_NL_GIS');
  });

  it('(د) يُعيد undefined لصفحة غير محروسة بعَلَم', () => {
    expect(advancedFeatureForPage('dashboard')).toBeUndefined();
  });
});

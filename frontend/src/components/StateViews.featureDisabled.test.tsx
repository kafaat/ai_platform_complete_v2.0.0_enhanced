// اختبارات FeatureDisabledState — الإصلاح الجوهريّ: بدل 404 خام/فراغ، لوحة واضحة
// باسم العَلَم الخلفيّ (FEATURE_X) ودرجة النضج. (أ) لصفحة محروسة تعرض العنوان
// «هذه الميزة غير مُفعَّلة» + اسم العَلَم + شارة النضج؛ (ب) لصفحة غير محروسة تسقط
// إلى رسالة عامّة آمنة بلا تعطّل؛ (ج) isFeatureDisabledError تكشف 404 فقط.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FeatureDisabledState, isFeatureDisabledError } from './StateViews';

describe('FeatureDisabledState — لوحة «ميزة غير مُفعَّلة»', () => {
  it('(أ) صفحة محروسة ⇒ تعرض اسم العَلَم الخلفيّ ونصّ «غير مُفعَّلة»', () => {
    render(<FeatureDisabledState page="nl-gis" />);
    expect(screen.getByText(/الميزة غير مُفعَّلة/)).toBeInTheDocument();
    // اسم العَلَم الخلفيّ المُطابِق يظهر (في العنوان والمتن).
    expect(screen.getAllByText(/FEATURE_NATURAL_LANGUAGE_GIS/).length).toBeGreaterThanOrEqual(1);
    // العنوان يطلب صراحةً ضبط العَلَم في الخادم (نصّ المهمّة).
    expect(screen.getByText(/تتطلّب ضبط FEATURE_NATURAL_LANGUAGE_GIS في الخادم/)).toBeInTheDocument();
  });

  it('(أ) تُظهر شارة درجة النضج (nl-gis = مبكّر/alpha)', () => {
    render(<FeatureDisabledState page="nl-gis" />);
    expect(screen.getByText('مبكّر')).toBeInTheDocument();
  });

  it('(أ) detail اختياريّ يَخلُف المتن الافتراضيّ', () => {
    render(<FeatureDisabledState page="device-twin" detail="نصّ مخصّص للاختبار" />);
    expect(screen.getByText('نصّ مخصّص للاختبار')).toBeInTheDocument();
  });

  it('(ب) صفحة غير محروسة ⇒ رسالة عامّة آمنة بلا تعطّل', () => {
    render(<FeatureDisabledState page="dashboard" />);
    expect(screen.getByText('هذه الميزة غير مُفعَّلة على الخادم')).toBeInTheDocument();
  });
});

describe('isFeatureDisabledError — كشف 404 فقط', () => {
  it('(ج) 404 ⇒ true', () => {
    expect(isFeatureDisabledError({ response: { status: 404 } })).toBe(true);
  });

  it('(ج) 503/401/أخطاء أخرى ⇒ false', () => {
    expect(isFeatureDisabledError({ response: { status: 503 } })).toBe(false);
    expect(isFeatureDisabledError({ response: { status: 401 } })).toBe(false);
    expect(isFeatureDisabledError(new Error('network'))).toBe(false);
    expect(isFeatureDisabledError(null)).toBe(false);
    expect(isFeatureDisabledError(undefined)).toBe(false);
  });
});

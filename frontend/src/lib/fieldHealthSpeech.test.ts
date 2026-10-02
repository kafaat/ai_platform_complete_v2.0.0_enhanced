// ملخّص «صحّة الحقل» المسموع: يُنطَق ما حضر وحده، ويُفرَّق صراحةً بين «لا بيانات»
// و«فشل الجلب»، ويُترجَم رفضُ سياسة الصوت إلى سببٍ مفهوم بدل ابتلاعه.
import { describe, it, expect } from 'vitest';
import {
  buildFieldHealthSpeech,
  isFieldHealthSettled,
  ttsErrorMessage,
  MAX_SPEECH_CHARS,
  type FieldHealthInput,
} from './fieldHealthSpeech';

const full: FieldHealthInput = {
  fieldName: 'سهول معين',
  crop: 'قمح صلب',
  ndvi: { state: 'ok', label: 'جيّد', value: 0.6234 },
  disease: { state: 'ok', riskAr: 'منخفض', adviceAr: 'تابع المراقبة الدوريّة.' },
  nitrogen: { state: 'ok', kgHa: 82.6 },
};

describe('buildFieldHealthSpeech', () => {
  it('ينطق الأقسام الحاضرة بقيمها', () => {
    const s = buildFieldHealthSpeech(full);
    expect(s).toContain('صحّة حقل سهول معين، المحصول قمح صلب.');
    expect(s).toContain('الغطاء النباتيّ: جيّد، بمؤشّر 0.62.');
    expect(s).toContain('خطر الأمراض: منخفض. تابع المراقبة الدوريّة.');
    expect(s).toContain('توصية النيتروجين: 83 كيلوغرام للهكتار.');
  });

  it('يفرّق «لا بيانات» عن «فشل الجلب» ولا يختلق رقماً', () => {
    const s = buildFieldHealthSpeech({
      ...full,
      ndvi: { state: 'empty' },
      disease: { state: 'error' },
      nitrogen: { state: 'disabled' },
    });
    expect(s).toContain('لا قراءة غطاء نباتيّ متاحة لهذا الحقل.');
    expect(s).toContain('تعذّر جلب تقدير خطر الأمراض الآن.');
    expect(s).toContain('خدمة التربة غير منشورة بعد');
    expect(s).not.toMatch(/مؤشّر\s+\d/);
    expect(s).not.toMatch(/\d+ كيلوغرام/);
  });

  it('قيمةٌ غير عدديّة مع حالة ok لا تُنطَق رقماً', () => {
    const s = buildFieldHealthSpeech({ ...full, ndvi: { state: 'ok', value: null }, nitrogen: { state: 'ok', kgHa: NaN } });
    expect(s).toContain('لا قراءة غطاء نباتيّ متاحة');
    expect(s).toContain('لا توصية تسميد متاحة');
  });

  it('يُسقط المحصول المجهول «—» ولا يتجاوز سقف الخدمة', () => {
    expect(buildFieldHealthSpeech({ ...full, crop: '—' })).toContain('صحّة حقل سهول معين.');
    const long = buildFieldHealthSpeech({ ...full, disease: { state: 'ok', riskAr: 'مرتفع', adviceAr: 'أ'.repeat(5000) } });
    expect(long.length).toBeLessThanOrEqual(MAX_SPEECH_CHARS);
  });
});

describe('isFieldHealthSettled', () => {
  it('لا يكتمل ما دام قسمٌ لم يصل', () => {
    expect(isFieldHealthSettled(full)).toBe(true);
    expect(isFieldHealthSettled({ ...full, ndvi: { state: 'loading' } })).toBe(false);
    expect(isFieldHealthSettled({ ...full, nitrogen: { state: 'error' } })).toBe(true);
  });
});

describe('ttsErrorMessage', () => {
  const blob = (o: unknown) => new Blob([JSON.stringify(o)], { type: 'application/json' });

  it('رفضُ السياسة (503) يُقال سبباً لا يُبتلَع — والجسمُ Blob كما يصل فعلاً', async () => {
    const err = {
      response: {
        status: 503,
        data: blob({ detail: { error: 'local_provider_unavailable_for_policy', policy_mode: 'local_only' } }),
      },
    };
    expect(await ttsErrorMessage(err)).toContain('سياسة مشاركة البيانات');
  });

  it('503 بلا رمز السياسة ليس رفضَ سياسة', async () => {
    const msg = await ttsErrorMessage({ response: { status: 503, data: blob({ detail: 'down' }) } });
    expect(msg).not.toContain('سياسة');
    expect(msg).toContain('غير متاحة الآن');
  });

  it('401 وغيابُ الاستجابة وجسمٌ غير JSON لهم رسائلُ صريحة', async () => {
    expect(await ttsErrorMessage({ response: { status: 401, data: blob({}) } })).toContain('سجّل الدخول');
    expect(await ttsErrorMessage(new Error('network'))).toContain('الشبكة');
    expect(await ttsErrorMessage({ response: { status: 500, data: new Blob(['<html>']) } })).toContain('غير متاحة الآن');
  });
});

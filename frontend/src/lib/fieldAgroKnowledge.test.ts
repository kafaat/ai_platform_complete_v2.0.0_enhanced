import { describe, expect, it } from 'vitest';
import {
  DASH, orDash, isCoffeeCrop, propagationFacts, provenanceNotes,
  coffeeVarietyRows, coffeePestRows, practiceRows,
  type CropPropagation, type CoffeeVarieties, type CoffeePests, type PostharvestBestPractices,
} from './fieldAgroKnowledge';

describe('orDash — null ⇒ «—», server text passes through', () => {
  it('maps null/undefined/blank to the dash sentinel', () => {
    expect(orDash(null)).toBe(DASH);
    expect(orDash(undefined)).toBe(DASH);
    expect(orDash('   ')).toBe(DASH);
  });
  it('passes real server text through (trim only, no rewrite)', () => {
    expect(orDash('  نصّ الخادم  ')).toBe('نصّ الخادم');
    expect(orDash(0)).toBe('0');
  });
});

describe('isCoffeeCrop — explicit match, no guessing', () => {
  it('matches Arabic/English coffee labels (with ال and diacritics)', () => {
    expect(isCoffeeCrop('بُنّ')).toBe(true);
    expect(isCoffeeCrop('البنّ')).toBe(true);
    expect(isCoffeeCrop('قهوة')).toBe(true);
    expect(isCoffeeCrop('Coffee')).toBe(true);
    expect(isCoffeeCrop('بنّ يمني')).toBe(true);
    expect(isCoffeeCrop('coffea arabica')).toBe(true);
  });
  it('does not match non-coffee crops or empty', () => {
    expect(isCoffeeCrop('قمح')).toBe(false);
    expect(isCoffeeCrop('wheat')).toBe(false);
    expect(isCoffeeCrop(null)).toBe(false);
    expect(isCoffeeCrop('')).toBe(false);
  });
});

describe('propagationFacts — real fields only, dropped when missing', () => {
  it('drops everything when unsupported', () => {
    const d: CropPropagation = { supported: false, message_ar: 'لا توصية' };
    expect(propagationFacts(d)).toEqual([]);
  });
  it('builds facts only from present server fields (no fabrication)', () => {
    const d: CropPropagation = {
      supported: true, crop: 'mango', recommended_method: 'grafting',
      method_name_ar: 'التطعيم (Grafting)', why_ar: 'يثمر أسرع', // method_tip_ar غائب عمداً
    };
    const facts = propagationFacts(d);
    expect(facts).toHaveLength(2);
    expect(facts[0]).toEqual({ label: 'الطريقة المُوصى بها', value: 'التطعيم (Grafting)' });
    expect(facts.some((f) => f.label === 'نصيحة')).toBe(false);
  });
});

describe('provenanceNotes — preserves note/source/disclaimer, drops absent', () => {
  it('collects only present provenance strings in stable order', () => {
    const post: PostharvestBestPractices = {
      practices_ar: [],
      principle_ar: 'التجفيف + النظافة',
      yemen_context_ar: 'الفقد بعد الحصاد',
      disclaimer_ar: 'إرشاد عامّ',
    };
    expect(provenanceNotes(post as unknown as Record<string, unknown>)).toEqual([
      'التجفيف + النظافة', 'الفقد بعد الحصاد', 'إرشاد عامّ',
    ]);
  });
  it('returns empty for null and ignores blank fields', () => {
    expect(provenanceNotes(null)).toEqual([]);
    expect(provenanceNotes({ note_ar: '  ', disclaimer_ar: 'حقيقيّ' })).toEqual(['حقيقيّ']);
  });
});

describe('coffee rows — keep note_ar/scientific, missing ⇒ «—»', () => {
  it('maps variety rows and dashes missing note', () => {
    const v: CoffeeVarieties = {
      varieties: [
        { name_ar: 'الحرازي', region_ar: 'حراز', note_ar: 'نكهة معقّدة' },
        { name_ar: 'المطري', region_ar: 'بني مطر' }, // note_ar غائب
      ],
    };
    const rows = coffeeVarietyRows(v);
    expect(rows[0]).toEqual({ name: 'الحرازي', region: 'حراز', note: 'نكهة معقّدة' });
    expect(rows[1].note).toBe(DASH);
    expect(coffeeVarietyRows(null)).toEqual([]);
  });
  it('maps pest rows preserving scientific name', () => {
    const p: CoffeePests = {
      pests_ar: [{ name_ar: 'صدأ الأوراق', scientific: 'Hemileia vastatrix', note_ar: 'فطري' }],
      ipm_note_ar: 'نهج IPM',
    };
    expect(coffeePestRows(p)[0]).toEqual({
      name: 'صدأ الأوراق', scientific: 'Hemileia vastatrix', note: 'فطري',
    });
  });
});

describe('practiceRows — drops fully empty rows, dashes partial', () => {
  it('keeps rows with any content, drops empty ones', () => {
    const rows = practiceRows([
      { topic_ar: 'التجفيف', detail_ar: 'جفّف ≤12%' },
      { topic_ar: '', detail_ar: '' },
      { topic_ar: 'النظافة', detail_ar: null },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[1]).toEqual({ topic: 'النظافة', detail: DASH });
    expect(practiceRows(undefined)).toEqual([]);
  });
});

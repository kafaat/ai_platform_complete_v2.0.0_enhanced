import { describe, expect, it } from 'vitest';
import {
  calendarFacts,
  plantingFitTone,
  topProverbs,
  type CalendarTodayContext,
} from './yemeniCalendar';

const ctx: CalendarTodayContext = {
  display_only: true,
  used_in_decision_engine: false,
  date_iso: '2026-07-04',
  active_mansion: {
    order: 8, name_ar: 'النثرة', approx_start_ar: '17/7', duration_days: 13,
    season_ar: 'الخريف', note_ar: 'أمطار صيفيّة — عمار الأرض',
  },
  himyarite_month: { order: 4, name_ar: 'ذو مبكر', approx_gregorian_ar: 'يوليو', meaning_ar: 'البواكير', season_himyari_ar: 'خرف' },
  regional_profile: {
    region_ar: 'المرتفعات الشماليّة', governorates_ar: ['صنعاء'], primary_system_ar: 'نجوم المعالم',
    structure_ar: '', source_ar: '', notes_ar: '',
  },
};

describe('calendarFacts — display facts only, server error passes as empty', () => {
  it('extracts mansion + himyarite + regional facts', () => {
    const facts = calendarFacts(ctx);
    expect(facts.map((f) => f.label)).toEqual(['المنزلة القمريّة', 'دلالتها', 'الشهر الحميريّ', 'نظام المنطقة']);
    expect(facts[0].value).toBe('النثرة (الخريف)');
    expect(facts[2].value).toBe('ذو مبكر — خرف');
  });
  it('is empty for error or missing context (no fabrication)', () => {
    expect(calendarFacts({ ...ctx, error_ar: 'تاريخ غير صالح' })).toEqual([]);
    expect(calendarFacts(null)).toEqual([]);
  });
  it('drops absent sections', () => {
    const facts = calendarFacts({ ...ctx, active_mansion: null, himyarite_month: null });
    expect(facts.map((f) => f.label)).toEqual(['نظام المنطقة']);
  });
});

describe('plantingFitTone — mirrors server status', () => {
  it('maps optimal/acceptable/off_window', () => {
    expect(plantingFitTone({ supported: true, status: 'optimal' })).toBe('good');
    expect(plantingFitTone({ supported: true, status: 'acceptable' })).toBe('ok');
    expect(plantingFitTone({ supported: true, status: 'off_window' })).toBe('bad');
  });
  it('is unknown for unsupported crops or missing fit', () => {
    expect(plantingFitTone({ supported: false, message_ar: 'غير مدعوم' })).toBe('unknown');
    expect(plantingFitTone(null)).toBe('unknown');
  });
});

describe('topProverbs', () => {
  it('slices proverbs and rejects error responses', () => {
    const p = { text_ar: 'إذا طلع سهيل…', meaning_ar: 'م', marker_ar: 'سهيل' };
    expect(topProverbs({ proverbs: [p, p, p] }, 2)).toHaveLength(2);
    expect(topProverbs({ proverbs: [p], error_ar: 'x' })).toEqual([]);
    expect(topProverbs(null)).toEqual([]);
  });
});

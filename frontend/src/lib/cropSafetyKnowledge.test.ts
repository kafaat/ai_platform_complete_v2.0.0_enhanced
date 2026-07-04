import { describe, expect, it } from 'vitest';
import {
  bannedRows,
  chemicalLimitFacts,
  chemicalStatusColor,
  highValueDetailRows,
  introductionCandidates,
  nicheDetailRows,
  pestRows,
  plantingCropRows,
  plantingWindowFacts,
  serverUnsupportedMessage,
  severityColor,
  textOrDash,
} from './cropSafetyKnowledge';

describe('chemicalStatusColor — تلوين عرضيّ لحكم الخادم فقط، المجهول محايد', () => {
  it('colors the three server statuses case-insensitively', () => {
    expect(chemicalStatusColor('ok')).toBe('#86efac');
    expect(chemicalStatusColor('WARNING')).toBe('#fdba74');
    expect(chemicalStatusColor('blocked')).toBe('#fca5a5');
  });
  it('is neutral for unknown/missing (no invented verdict)', () => {
    expect(chemicalStatusColor('weird')).toBe('#64748b');
    expect(chemicalStatusColor(null)).toBe('#64748b');
  });
});

describe('severityColor — سلّم riskColor نفسه، المجهول محايد', () => {
  it('colors known severities case-insensitively', () => {
    expect(severityColor('CRITICAL')).toBe('#fca5a5');
    expect(severityColor('high')).toBe('#fdba74');
    expect(severityColor('MEDIUM')).toBe('#fde68a');
  });
  it('is neutral for unknown/missing', () => {
    expect(severityColor('odd')).toBe('#64748b');
    expect(severityColor(undefined)).toBe('#64748b');
  });
});

describe('textOrDash — الغائب «—» لا تصفير', () => {
  it('passes server text through and dashes the absent', () => {
    expect(textOrDash('نصّ الخادم')).toBe('نصّ الخادم');
    expect(textOrDash('  ')).toBe('—');
    expect(textOrDash(null)).toBe('—');
  });
});

describe('chemicalLimitFacts — أرقام الخادم كما هي، الغائب يسقط', () => {
  it('builds only present limits', () => {
    const facts = chemicalLimitFacts({ status: 'ok', max_kg_ha: 2, buffer_zone_m: 5, reentry_hours: 4 });
    expect(facts).toEqual([
      { label: 'الحدّ الأقصى', value: '2 كجم/هكتار' },
      { label: 'المنطقة العازلة', value: '5 م' },
      { label: 'إعادة الدخول', value: '4 ساعة' },
    ]);
  });
  it('drops nulls honestly (blocked responses carry no limits)', () => {
    expect(chemicalLimitFacts({ status: 'blocked', max_kg_ha: null })).toEqual([]);
    expect(chemicalLimitFacts(null)).toEqual([]);
  });
});

describe('bannedRows + pestRows + plantingCropRows — قوائم الخادم كما هي', () => {
  it('returns server arrays untouched', () => {
    expect(bannedRows({ chemicals: [{ name: 'ddt', severity: 'CRITICAL' }] })).toHaveLength(1);
    expect(pestRows({ pests: [{ name_ar: 'سوسة الأرز' }] })[0].name_ar).toBe('سوسة الأرز');
    expect(plantingCropRows({ crops: [{ crop: 'wheat', name_ar: 'القمح' }] })[0].crop).toBe('wheat');
  });
  it('is empty for missing input', () => {
    expect(bannedRows(null)).toEqual([]);
    expect(pestRows(undefined)).toEqual([]);
    expect(plantingCropRows({})).toEqual([]);
  });
});

describe('plantingWindowFacts + serverUnsupportedMessage — حكم supported من الخادم', () => {
  it('builds facts only for supported windows', () => {
    const facts = plantingWindowFacts({
      supported: true, season_ar: 'شتوي', window_ar: 'نوفمبر، ديسمبر، يناير', optimal_ar: 'نوفمبر، ديسمبر', harvest_ar: 'أبريل، مايو',
    });
    expect(facts.map((f) => f.label)).toEqual(['الموسم', 'النافذة', 'الأمثل', 'الحصاد']);
  });
  it('is empty when unsupported/missing and surfaces message_ar verbatim', () => {
    expect(plantingWindowFacts({ supported: false, message_ar: 'لا تقويم' })).toEqual([]);
    expect(plantingWindowFacts(null)).toEqual([]);
    expect(serverUnsupportedMessage({ supported: false, message_ar: 'لا تقويم' })).toBe('لا تقويم');
    expect(serverUnsupportedMessage({ supported: true })).toBeNull();
    expect(serverUnsupportedMessage(null)).toBeNull();
  });
});

describe('highValueDetailRows — الحقول الموجودة فقط، بترتيب ثابت، النصّ حرفيّ', () => {
  it('keeps proven-tier fields present on the response', () => {
    const rows = highValueDetailRows({
      supported: true, name_ar: 'الجوجوبا', tier_ar: 'مثبت للجوف',
      type_ar: 'شجيرة زيتيّة', water_ar: 'منخفض جدّاً', evidence_ar: 'ذهب الصحراء',
    });
    expect(rows.map((r) => r.key)).toEqual(['type_ar', 'water_ar', 'evidence_ar']);
    expect(rows[0].value).toBe('شجيرة زيتيّة');
  });
  it('keeps not-suited reason and is empty when unsupported', () => {
    expect(highValueDetailRows({ supported: true, reason_ar: 'استوائي' })[0].label).toBe('السبب');
    expect(highValueDetailRows({ supported: false, message_ar: 'لا تفصيل' })).toEqual([]);
    expect(highValueDetailRows(null)).toEqual([]);
  });
});

describe('nicheDetailRows — نفس الصدق للمنتجات المتخصّصة', () => {
  it('maps present fields with display labels', () => {
    const rows = nicheDetailRows({
      supported: true, name_ar: 'الصمغ العربي', category_ar: 'صمغ صناعي', yemen_edge_ar: 'الأكاسيا موجودة أصلاً',
    });
    expect(rows).toEqual([
      { key: 'category_ar', label: 'الفئة', value: 'صمغ صناعي' },
      { key: 'yemen_edge_ar', label: 'الميزة اليمنيّة', value: 'الأكاسيا موجودة أصلاً' },
    ]);
  });
  it('is empty when unsupported/missing', () => {
    expect(nicheDetailRows({ supported: false })).toEqual([]);
    expect(nicheDetailRows(undefined)).toEqual([]);
  });
});

describe('introductionCandidates — ترشيح الخادم حسب المنطقة كما هو', () => {
  it('returns server candidates untouched', () => {
    const out = introductionCandidates({
      zone_query: 'jawf',
      candidates: [{ crop: 'moringa', name_ar: 'المورينجا', zone: 'jawf' }],
    });
    expect(out).toHaveLength(1);
    expect(out[0].name_ar).toBe('المورينجا');
  });
  it('is empty for missing input', () => {
    expect(introductionCandidates(null)).toEqual([]);
    expect(introductionCandidates({})).toEqual([]);
  });
});
